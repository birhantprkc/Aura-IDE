from __future__ import annotations

from typing import Any

from aura.conversation.tools._types import ToolExecResult
from aura.drones.store import DroneStore


class MissionHandlersMixin:
    """Mixin for ToolRegistry implementing Mission Control tool handlers."""

    def _handle_list_missions(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        """List all saved Mission Control workflows."""
        from aura.conversation.mission_snapshot import build_mission_list

        missions = build_mission_list(self._root)
        return ToolExecResult(
            ok=True,
            payload={"ok": True, "missions": missions},
        )

    def _handle_inspect_mission(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        """Inspect a single mission by id or name."""
        chain_id = (args.get("id") or "").strip() or None
        name = (args.get("name") or "").strip() or None

        from aura.conversation.mission_snapshot import (
            find_chain_by_name_or_id,
            resolve_mission_snapshot,
        )

        chain = find_chain_by_name_or_id(self._root, name, chain_id)
        if chain is None:
            return ToolExecResult(
                ok=False,
                payload={
                    "ok": False,
                    "error": f"mission not found: id={chain_id}, name={name}",
                },
            )

        snapshot = resolve_mission_snapshot(self._root, chain.id)
        if not snapshot.get("ok"):
            return ToolExecResult(ok=False, payload=snapshot)

        # Try live Workbay overlay
        snapshot["source"] = "saved_storage"
        try:
            from aura.hooks import hooks

            live = hooks.trigger("query_mission_workbay_state")
            if live and isinstance(live, dict) and live.get("chain_id") == chain.id:
                snapshot["source"] = "live_workbay"
                chain_data = snapshot.setdefault("chain", {})
                for key in ("name", "description", "nodes", "edges", "goals", "mission_core"):
                    if key in live:
                        chain_data[key] = live[key]
                if live.get("drone_lookup"):
                    snapshot["drone_lookup"] = live["drone_lookup"]
        except RuntimeError:
            pass  # no handler registered — not running in GUI context

        return ToolExecResult(ok=True, payload=snapshot)

    def _handle_mission_control_state(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        """Get the current Mission Control state."""
        from aura.conversation.mission_snapshot import (
            find_chain_by_name_or_id,
            resolve_mission_snapshot,
        )

        chain_id = (args.get("id") or "").strip() or None
        name = (args.get("name") or "").strip() or None

        if chain_id or name:
            chain = find_chain_by_name_or_id(self._root, name, chain_id)
            target_id = chain.id if chain else None
        else:
            # Try the active Workbay tab
            target_id = None
            try:
                from aura.hooks import hooks

                live = hooks.trigger("query_mission_workbay_state")
                if live and isinstance(live, dict) and live.get("chain_id"):
                    target_id = live["chain_id"]
            except RuntimeError:
                pass

            if not target_id:
                # Fall back to the first saved chain
                from aura.drones.chain_store import ChainStore

                chains = ChainStore.list_chains(self._root)
                if chains:
                    target_id = chains[0].id

        if not target_id:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": "no missions found"},
            )

        snapshot = resolve_mission_snapshot(self._root, target_id)
        if not snapshot.get("ok"):
            return ToolExecResult(ok=False, payload=snapshot)

        # Try Workbay overlay
        snapshot["source"] = "saved_storage"
        try:
            from aura.hooks import hooks

            live = hooks.trigger("query_mission_workbay_state")
            if live and isinstance(live, dict) and live.get("chain_id") == target_id:
                snapshot["source"] = "live_workbay"
                chain_data = snapshot.setdefault("chain", {})
                for key in ("name", "description", "nodes", "edges", "goals", "mission_core"):
                    if key in live:
                        chain_data[key] = live[key]
                if live.get("drone_lookup"):
                    snapshot["drone_lookup"] = live["drone_lookup"]
        except RuntimeError:
            pass

        return ToolExecResult(ok=True, payload=snapshot)

    def _handle_rename_mission(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        """Rename a saved mission."""
        chain_id = (args.get("id") or "").strip() or None
        name = (args.get("name") or "").strip() or None
        new_name = (args.get("new_name") or "").strip()

        if not new_name:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": "new_name is required"},
            )

        from aura.conversation.mission_snapshot import find_chain_by_name_or_id

        chain = find_chain_by_name_or_id(self._root, name, chain_id)
        if chain is None:
            return ToolExecResult(
                ok=False,
                payload={
                    "ok": False,
                    "error": f"mission not found: id={chain_id}, name={name}",
                },
            )

        # Load raw dict, modify name, save back
        from aura.drones.chain_store import load_chain, save_chain

        data = load_chain(self._root, chain.id)
        if data is None:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": f"failed to load mission data: {chain.id}"},
            )

        old_name = data.get("name", "")
        data["name"] = new_name
        save_chain(self._root, chain.id, data)

        return ToolExecResult(
            ok=True,
            payload={
                "ok": True,
                "renamed": True,
                "id": chain.id,
                "old_name": old_name,
                "new_name": new_name,
            },
        )

    def _handle_run_mission(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        """Run a saved mission if all drones are read-only."""
        chain_id = (args.get("id") or "").strip() or None
        name = (args.get("name") or "").strip() or None

        from aura.conversation.mission_snapshot import find_chain_by_name_or_id

        chain = find_chain_by_name_or_id(self._root, name, chain_id)
        if chain is None:
            return ToolExecResult(
                ok=False,
                payload={
                    "ok": False,
                    "error": f"mission not found: id={chain_id}, name={name}",
                },
            )

        # Build drone lookup
        drones = DroneStore.list_drones(self._root)
        drone_lookup = {d.id: d for d in drones}

        # Check for missing drones
        missing = [n.drone_id for n in chain.nodes if n.drone_id not in drone_lookup]
        if missing:
            return ToolExecResult(
                ok=False,
                payload={
                    "ok": False,
                    "error": f"missing drones: {', '.join(missing)}",
                },
            )

        # Classify write-capable nodes
        from aura.drones.chain_runner import (
            classify_consequential_nodes,
            run_chain,
        )

        consequential = classify_consequential_nodes(chain, drone_lookup)
        if consequential:
            write_drones = [
                {
                    "node_id": c["node_id"],
                    "drone_id": c["drone_id"],
                    "drone_name": c["drone_name"],
                    "write_policy": c["write_policy"],
                }
                for c in consequential
            ]
            return ToolExecResult(
                ok=True,
                payload={
                    "ok": True,
                    "approval_required": True,
                    "message": (
                        f"Workflow '{chain.name}' contains write-capable drones. "
                        "Approve through the Workbay UI."
                    ),
                    "workflow_name": chain.name,
                    "workflow_id": chain.id,
                    "write_capable_drones": write_drones,
                },
            )

        # All read-only — execute synchronously
        try:
            result = run_chain(
                self._root,
                chain,
                drone_lookup=drone_lookup,
            )
        except Exception as e:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": str(e)},
            )

        # Summarise node results
        node_results = []
        for nid, nr in result.node_runs.items():
            node_results.append({
                "node_id": nid,
                "drone_id": nr.get("drone_id", ""),
                "status": nr.get("status", "unknown"),
                "met": nr.get("met"),
                "error": nr.get("error", ""),
            })

        return ToolExecResult(
            ok=True,
            payload={
                "ok": True,
                "run_id": result.run_id,
                "status": result.status,
                "node_results": node_results,
                "workflow_name": chain.name,
                "workflow_id": chain.id,
            },
        )
