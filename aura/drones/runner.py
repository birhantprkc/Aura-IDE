"""DroneRunner — executes a read-only Drone on a background QThread."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from aura.backends.api import APIAgentBackend
from aura.client.events import (
    ApiError,
    ContentDelta,
    Done,
    ReasoningDelta,
    ToolCallArgsDelta,
    ToolCallEnd,
    ToolCallStart,
    Usage,
)
from aura.config import get_provider, resolve_role_default_model
from aura.conversation.tools._types import ApprovalDecision
from aura.conversation.tools.registry import ToolRegistry
from aura.drones.definition import DroneDefinition
from aura.drones.receipt import DroneReceipt
from aura.drones.run import DroneRun

logger = logging.getLogger(__name__)


class DroneRunner(QObject):
    """Executes a single read-only Drone on a background thread.

    Usage:
        thread = QThread(self)
        runner = DroneRunner(workspace_root, drone)
        runner.moveToThread(thread)
        thread.started.connect(runner.run)
        runner.finished.connect(thread.quit)
        thread.start()
    """

    # --- Qt signals for the GUI thread ---
    statusChanged = Signal(str)            # status string: summoning/running/...
    contentDelta = Signal(str)             # text chunk from LLM
    toolCallStart = Signal(int, str, str)  # index, id, name
    toolCallArgsDelta = Signal(int, str)   # index, args_chunk
    toolCallEnd = Signal(int)              # index
    toolResult = Signal(str, str, bool, str)  # tool_call_id, name, ok, result
    usageEmitted = Signal(int, int, int, int)  # prompt, completion, cache_hit, cache_miss
    apiError = Signal(int, str)            # status_code, message
    receiptReady = Signal(object)          # DroneReceipt
    finished = Signal()

    def __init__(
        self,
        workspace_root: Path,
        drone: DroneDefinition,
        provider_id: str | None = None,
        model: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace_root = workspace_root
        self._drone = drone
        self._run = DroneRun(drone=drone)
        self._provider = provider_id
        self._model = model

    def cancel(self) -> None:
        """Request cancellation (thread-safe)."""
        self._run.cancel()

    @property
    def run_state(self) -> DroneRun:
        return self._run

    @Slot()
    def run(self) -> None:
        """Main execution method — runs on the QThread.

        Creates a read-only ToolRegistry, builds messages from the drone's
        instructions, loops through the agent backend until done or cancelled.
        """
        logger.info("Drone run started: %s (%s)", self._drone.name, self._run.run_id)
        self._run.mark("running")
        self.statusChanged.emit("running")

        # 1. Create read-only tool registry
        registry = ToolRegistry(
            workspace_root=self._workspace_root,
            read_only=True,
            mode="single",
        )

        # 2. Filter to allowed tools if specified
        tool_defs = registry.tool_defs()
        if self._drone.allowed_tools:
            allowed_set = set(self._drone.allowed_tools)
            tool_defs = [t for t in tool_defs if t.get("function", {}).get("name") in allowed_set]

        # 3. Build messages
        system_prompt = self._build_system_prompt()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._drone.instructions},
        ]

        # 4. Resolve provider/model
        provider_id = self._provider or "deepseek"
        provider_cfg = get_provider(provider_id)
        model = self._model or resolve_role_default_model(provider_id, "worker") or provider_cfg.models.get("worker", "")

        # 5. Create backend
        backend = APIAgentBackend(provider=provider_id)

        # 6. Run the agent loop
        tool_calls_made = 0
        tool_errors = 0
        max_rounds = self._drone.budget.max_tool_rounds
        timeout = self._drone.budget.timeout_seconds
        start_time = time.time()

        # Approval callback — always approve since we're in read-only mode
        # and write tools aren't available to the model.
        def _always_approve(_request) -> ApprovalDecision:
            return ApprovalDecision(action="approve")

        try:
            for _round_num in range(max_rounds):
                if self._run.cancel_event.is_set():
                    self._run.mark("cancelled")
                    self.statusChanged.emit("cancelled")
                    break

                if time.time() - start_time > timeout:
                    self._run.mark("timed_out")
                    self.statusChanged.emit("timed_out")
                    break

                # Call the LLM
                stream = backend.stream(
                    messages=messages,
                    tools=tool_defs if tool_defs else None,
                    model=model,
                    thinking="off",
                    cancel_event=self._run.cancel_event,
                    temperature=0.7,
                )

                full_message: dict[str, Any] | None = None
                finish_reason: str | None = None

                for event in stream:
                    if self._run.cancel_event.is_set():
                        break

                    if isinstance(event, ContentDelta):
                        self.contentDelta.emit(event.text)
                    elif isinstance(event, ReasoningDelta):
                        pass  # skip reasoning in drone output
                    elif isinstance(event, ToolCallStart):
                        self.toolCallStart.emit(event.index, event.id, event.name)
                    elif isinstance(event, ToolCallArgsDelta):
                        self.toolCallArgsDelta.emit(event.index, event.args_chunk)
                    elif isinstance(event, ToolCallEnd):
                        self.toolCallEnd.emit(event.index)
                    elif isinstance(event, Usage):
                        self.usageEmitted.emit(
                            event.prompt_tokens, event.completion_tokens,
                            event.cache_hit_tokens, event.cache_miss_tokens,
                        )
                    elif isinstance(event, Done):
                        finish_reason = event.finish_reason
                        full_message = event.full_message
                    elif isinstance(event, ApiError):
                        self.apiError.emit(event.status_code or -1, event.message)
                        self._run.mark("failed")
                        self.statusChanged.emit("failed")
                        break

                if self._run.cancel_event.is_set():
                    self._run.mark("cancelled")
                    self.statusChanged.emit("cancelled")
                    break

                if finish_reason == "tool_calls" and full_message:
                    tool_calls = full_message.get("tool_calls", [])
                    if not tool_calls:
                        # No more tool calls — done
                        break

                    # Append assistant message to history
                    messages.append(full_message)

                    # Execute each tool call
                    tool_results_content: list[dict[str, Any]] = []
                    for tc in tool_calls:
                        tool_call_id = tc["id"]
                        name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except (json.JSONDecodeError, KeyError):
                            args = {}

                        tool_calls_made += 1

                        # Execute via registry
                        try:
                            result = registry.execute(name, args, approval_cb=_always_approve)
                            ok = result.ok
                            result_str = result.to_tool_message_content()
                            if not ok:
                                tool_errors += 1
                        except Exception as exc:
                            ok = False
                            result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)
                            tool_errors += 1

                        # Emit result for UI
                        self.toolResult.emit(tool_call_id, name, ok, result_str)

                        # Build tool result for next API call
                        tool_results_content.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result_str,
                        })

                    # Append tool results and continue loop
                    messages.extend(tool_results_content)
                    continue  # next round

                elif finish_reason in ("stop", "end_turn", None):
                    # Normal completion — no more tool calls
                    self._run.mark("completed")
                    self.statusChanged.emit("completed")
                    break

                else:
                    # Unknown finish_reason — treat as done
                    self._run.mark("completed")
                    self.statusChanged.emit("completed")
                    break

            else:
                # Loop exhausted without break — max rounds reached
                self._run.mark("completed")
                self.statusChanged.emit("completed")

        except Exception as exc:
            logger.exception("Drone runner error")
            if not self._run.cancel_event.is_set():
                self._run.mark("failed")
                self.statusChanged.emit("failed")
                self.apiError.emit(-1, str(exc))

        finally:
            # Build and emit receipt
            ended = dt.datetime.now(dt.timezone.utc).isoformat()
            receipt = DroneReceipt(
                run_id=self._run.run_id,
                drone_id=self._drone.id,
                drone_name=self._drone.name,
                status=self._run.status,
                started_at=dt.datetime.fromtimestamp(self._run.started_at, tz=dt.timezone.utc).isoformat(),
                ended_at=ended,
                tool_calls_made=tool_calls_made,
                tool_errors=tool_errors,
                summary="",
                output_contract=self._drone.output_contract,
            )
            self.receiptReady.emit(receipt)
            self.finished.emit()

    def _build_system_prompt(self) -> str:
        """Build the system prompt for this drone."""
        budget_min = max(1, self._drone.budget.timeout_seconds // 60)
        return (
            f"You are a focused, read-only worker drone: \"{self._drone.name}\".\n\n"
            f"{self._drone.description}\n\n"
            f"## Instructions\n{self._drone.instructions}\n\n"
            f"## Rules\n"
            f"- Read-only mode: you cannot write or modify any files.\n"
            f"- Execute the task using the available tools.\n"
            f"- Provide a clear summary of what you found or accomplished.\n"
            f"- Keep responses concise and relevant.\n"
            f"- Budget: {self._drone.budget.max_tool_rounds} tool rounds, {budget_min} minute timeout.\n\n"
            f"## Output contract\n{self._drone.output_contract}"
        )
