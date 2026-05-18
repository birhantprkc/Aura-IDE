"""Modal Settings dialog — exposes the persisted AppSettings + a few
read-only environment / workspace facts.
"""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from aura.config import (
    APP_NAME,
    AppSettings,
    fetch_provider_models,
    get_api_key,
    save_dynamic_catalog,
    save_settings,
    set_api_key,
)
from aura.providers.base import ProviderId
from aura.providers.registry import provider_registry
from aura.gui.theme import FG_DIM, SUCCESS, WARN
from aura.gui.aura_widget import GlassSwitch

logger = logging.getLogger(__name__)

_THINKING_ITEMS: list[tuple[str, str]] = [
    ("Off", "off"),
    ("High", "high"),
    ("Max", "max"),
]


class DiscoveryWorker(QObject):
    """Background worker for model discovery."""
    finished = Signal(str, dict, dict, str)  # provider_id, models, pricing, error_msg

    def __init__(self, provider_id: ProviderId):
        super().__init__()
        self.provider_id = provider_id

    def run(self):
        try:
            models, pricing, error = fetch_provider_models(self.provider_id)
            self.finished.emit(self.provider_id, models, pricing, error or "")
        except Exception as exc:
            self.finished.emit(self.provider_id, {}, {}, str(exc))


class SettingsDialog(QDialog):
    """Modal settings.

    `on_change_root` is fired when the user clicks "Change..." next to the
    workspace label so the host (MainWindow) can run the same picker it uses
    elsewhere; we don't fork that logic here.
    """

    def __init__(
        self,
        settings: AppSettings,
        workspace_root: Path | None,
        on_change_root: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setModal(True)
        self.resize(580, 0)

        self._settings = copy.deepcopy(settings)
        self._on_change_root = on_change_root

        # Discovery tracking
        self._discovery_inflight: set[str] = set()
        self._discovery_thread: QThread | None = None
        self._discovery_worker: DiscoveryWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(14)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(420)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 10, 0)
        content_layout.setSpacing(0)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        # ---- API Key input (planner provider) ----
        api_key_row = QHBoxLayout()
        api_key_row.setSpacing(6)

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Paste API key here...")
        api_key_row.addWidget(self._api_key_input, 1)

        self._save_key_btn = QPushButton("Save")
        self._save_key_btn.setToolTip("Encrypt and store this key on disk")
        self._save_key_btn.clicked.connect(self._on_save_api_key)
        api_key_row.addWidget(self._save_key_btn)

        self._clear_key_btn = QPushButton("Clear")
        self._clear_key_btn.setToolTip("Remove stored key for this provider")
        self._clear_key_btn.clicked.connect(self._on_clear_api_key)
        api_key_row.addWidget(self._clear_key_btn)

        api_key_widget = QWidget()
        api_key_widget.setLayout(api_key_row)
        form.addRow("API Key:", api_key_widget)

        self._api_key_status = QLabel("")
        self._api_key_status.setWordWrap(True)
        form.addRow("", self._api_key_status)

        planner_provider = self._settings.planner_provider
        self._refresh_api_key_status(planner_provider)

        # ---- Tavily API Key ----
        tavily_sep = QLabel("Web Search (Tavily)")
        tavily_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", tavily_sep)

        tavily_key_row = QHBoxLayout()
        tavily_key_row.setSpacing(6)
        self._tavily_key_input = QLineEdit()
        self._tavily_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._tavily_key_input.setPlaceholderText("Paste Tavily API key here...")
        tavily_key_row.addWidget(self._tavily_key_input, 1)

        self._save_tavily_btn = QPushButton("Save")
        self._save_tavily_btn.clicked.connect(self._on_save_tavily_key)
        tavily_key_row.addWidget(self._save_tavily_btn)

        self._clear_tavily_btn = QPushButton("Clear")
        self._clear_tavily_btn.clicked.connect(self._on_clear_tavily_key)
        tavily_key_row.addWidget(self._clear_tavily_btn)

        tavily_widget = QWidget()
        tavily_widget.setLayout(tavily_key_row)
        form.addRow("Tavily Key:", tavily_widget)

        self._tavily_status = QLabel("")
        self._tavily_status.setWordWrap(True)
        form.addRow("", self._tavily_status)
        self._refresh_tavily_status()

        # ---- P/W mode toggle ----
        self._restore_chk = GlassSwitch(
            "Restore most-recent conversation on launch",
            self._settings.restore_last_conversation,
        )
        form.addRow("", self._restore_chk)

        self._pw_mode_chk = GlassSwitch(
            "Planner/Worker mode (planner chats; worker executes code changes)",
            self._settings.planner_worker_mode,
        )
        self._pw_mode_chk.toggled.connect(self._on_pw_toggled)
        form.addRow("", self._pw_mode_chk)

        # Planner Provider
        self._planner_provider_combo = QComboBox()
        for pid in provider_registry.ids():
            spec = provider_registry.get(pid)
            self._planner_provider_combo.addItem(spec.label, pid)
        self._planner_provider_combo.setCurrentIndex(
            provider_registry.ids().index(self._settings.planner_provider)
        )
        self._planner_provider_combo.currentIndexChanged.connect(
            self._on_planner_provider_changed
        )
        form.addRow("Planner provider:", self._planner_provider_combo)

        self._planner_model_combo = QComboBox()
        form.addRow("Planner model:", self._planner_model_combo)

        self._planner_thinking_combo = QComboBox()
        for label, val in _THINKING_ITEMS:
            self._planner_thinking_combo.addItem(label, val)
        form.addRow("Planner thinking:", self._planner_thinking_combo)

        # Worker Provider
        self._worker_provider_combo = QComboBox()
        for pid in provider_registry.ids():
            spec = provider_registry.get(pid)
            self._worker_provider_combo.addItem(spec.label, pid)
        self._worker_provider_combo.setCurrentIndex(
            provider_registry.ids().index(self._settings.worker_provider)
        )
        self._worker_provider_combo.currentIndexChanged.connect(
            self._on_worker_provider_changed
        )
        form.addRow("Worker provider:", self._worker_provider_combo)

        self._worker_model_combo = QComboBox()
        form.addRow("Worker model:", self._worker_model_combo)

        self._worker_thinking_combo = QComboBox()
        for label, val in _THINKING_ITEMS:
            self._worker_thinking_combo.addItem(label, val)
        form.addRow("Worker thinking:", self._worker_thinking_combo)

        # Populate model combos
        self._populate_all_role_models()

        # Set thinking selections
        self._set_combo_to_data(
            self._planner_thinking_combo, self._settings.default_planner_thinking
        )
        self._set_combo_to_data(
            self._worker_thinking_combo, self._settings.default_worker_thinking
        )

        # --- Vision settings ---
        vision_sep = QLabel("Vision (Local Model)")
        vision_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", vision_sep)

        self._vision_enabled_chk = GlassSwitch(
            "Enable local vision model for image descriptions",
            self._settings.vision_enabled,
        )
        form.addRow("", self._vision_enabled_chk)

        self._vision_model_combo = QComboBox()
        self._vision_model_combo.setEditable(True)
        self._vision_model_combo.addItems(
            ["llama3.2-vision", "llava:13b", "minicpm-v", "bakllava"]
        )
        self._vision_model_combo.setCurrentText(self._settings.vision_model)
        form.addRow("Vision model:", self._vision_model_combo)

        self._vision_endpoint_combo = QComboBox()
        self._vision_endpoint_combo.setEditable(True)
        self._vision_endpoint_combo.addItems(["http://localhost:11434/v1"])
        self._vision_endpoint_combo.setCurrentText(self._settings.vision_endpoint)
        form.addRow("Vision endpoint:", self._vision_endpoint_combo)

        # --- Temperature ---
        temp_sep = QLabel("Temperature")
        temp_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", temp_sep)

        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.1)
        self._temperature_spin.setDecimals(1)
        self._temperature_spin.setToolTip(
            "Controls response randomness. 0 = deterministic, 2 = maximum creativity. "
            "Only applied when thinking is Off."
        )
        self._temperature_spin.setValue(self._settings.temperature)
        form.addRow("Temperature:", self._temperature_spin)

        self._worker_temperature_spin = QDoubleSpinBox()
        self._worker_temperature_spin.setRange(0.0, 2.0)
        self._worker_temperature_spin.setSingleStep(0.1)
        self._worker_temperature_spin.setDecimals(1)
        self._worker_temperature_spin.setToolTip(
            "Controls response randomness for the worker model. Lower = more deterministic."
        )
        self._worker_temperature_spin.setValue(self._settings.worker_temperature)
        form.addRow("Worker Temperature:", self._worker_temperature_spin)

        self._refresh_pw_enabled()

        # --- Automation ---
        auto_sep = QLabel("Automation")
        auto_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", auto_sep)

        self._auto_commit_chk = GlassSwitch(
            "Auto-commit changes after worker completes",
            self._settings.auto_commit_enabled,
        )
        form.addRow("", self._auto_commit_chk)

        self._auto_dispatch_chk = GlassSwitch(
            "Auto-dispatch: Send specs to worker without approval",
            self._settings.auto_dispatch,
        )
        form.addRow("", self._auto_dispatch_chk)

        self._auto_approve_chk = GlassSwitch(
            "Auto-approve: Apply file edits without diff approval",
            self._settings.auto_approve,
        )
        form.addRow("", self._auto_approve_chk)

        self._max_rounds_spin = QSpinBox()
        self._max_rounds_spin.setRange(1, 500)
        self._max_rounds_spin.setToolTip(
            "Maximum number of tool-call rounds allowed in a single user turn."
        )
        self._max_rounds_spin.setValue(self._settings.max_tool_rounds)
        form.addRow("Max tool rounds:", self._max_rounds_spin)

        # --- Sandbox ---
        sandbox_sep = QLabel("Execution Sandbox")
        sandbox_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", sandbox_sep)

        sandbox_note = QLabel(
            "Docker mode runs terminal commands and dynamic tools in an isolated container. "
            "Host mode runs them directly on your machine (fast but no isolation). "
            "Docker must be installed for Docker mode to work."
        )
        sandbox_note.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        sandbox_note.setWordWrap(True)
        form.addRow("", sandbox_note)

        self._sandbox_combo = QComboBox()
        self._sandbox_combo.addItem("Docker (recommended)", "docker")
        self._sandbox_combo.addItem("Host (no isolation)", "host")
        self._sandbox_combo.addItem("WASM (coming soon)", "wasm")
        form.addRow("Sandbox mode:", self._sandbox_combo)

        sandbox_idx = self._sandbox_combo.findData(self._settings.sandbox_mode)
        if sandbox_idx >= 0:
            self._sandbox_combo.setCurrentIndex(sandbox_idx)

        # --- System Prompts ---
        prompts_sep = QLabel("System Prompts")
        prompts_sep.setStyleSheet(
            f"color: {FG_DIM}; font-weight: 600; font-size: 11px;"
            " text-transform: uppercase; letter-spacing: 0.04em;"
        )
        form.addRow("", prompts_sep)

        prompts_note = QLabel(
            "Leave blank to use the built-in default. "
            "Custom prompts take effect on the next conversation turn."
        )
        prompts_note.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        prompts_note.setWordWrap(True)
        form.addRow("", prompts_note)

        from aura.prompts import (
            PLANNER_SYSTEM_PROMPT as _PLANNER_PROMPT,
            WORKER_SYSTEM_PROMPT as _WORKER_PROMPT,
            SINGLE_SYSTEM_PROMPT as _SINGLE_PROMPT,
        )

        # Single-mode prompt
        self._single_prompt_edit = QPlainTextEdit()
        self._single_prompt_edit.setFixedHeight(80)
        self._single_prompt_edit.setPlaceholderText(_SINGLE_PROMPT[:80] + "...")
        self._single_prompt_edit.setPlainText(self._settings.system_prompt)
        single_reset_btn = QPushButton("Reset")
        single_reset_btn.clicked.connect(lambda: self._single_prompt_edit.clear())
        single_row = QHBoxLayout()
        single_row.setSpacing(6)
        single_row.addWidget(self._single_prompt_edit, 1)
        single_row.addWidget(single_reset_btn)
        single_widget = QWidget()
        single_widget.setLayout(single_row)
        form.addRow("Single mode:", single_widget)

        # Planner prompt
        self._planner_prompt_edit = QPlainTextEdit()
        self._planner_prompt_edit.setFixedHeight(80)
        self._planner_prompt_edit.setPlaceholderText(_PLANNER_PROMPT[:80] + "...")
        self._planner_prompt_edit.setPlainText(self._settings.planner_system_prompt)
        planner_reset_btn = QPushButton("Reset")
        planner_reset_btn.clicked.connect(lambda: self._planner_prompt_edit.clear())
        planner_row = QHBoxLayout()
        planner_row.setSpacing(6)
        planner_row.addWidget(self._planner_prompt_edit, 1)
        planner_row.addWidget(planner_reset_btn)
        planner_widget = QWidget()
        planner_widget.setLayout(planner_row)
        form.addRow("Planner:", planner_widget)

        # Worker prompt
        self._worker_prompt_edit = QPlainTextEdit()
        self._worker_prompt_edit.setFixedHeight(80)
        self._worker_prompt_edit.setPlaceholderText(_WORKER_PROMPT[:80] + "...")
        self._worker_prompt_edit.setPlainText(self._settings.worker_system_prompt)
        worker_reset_btn = QPushButton("Reset")
        worker_reset_btn.clicked.connect(lambda: self._worker_prompt_edit.clear())
        worker_row = QHBoxLayout()
        worker_row.setSpacing(6)
        worker_row.addWidget(self._worker_prompt_edit, 1)
        worker_row.addWidget(worker_reset_btn)
        worker_widget = QWidget()
        worker_widget.setLayout(worker_row)
        form.addRow("Worker:", worker_widget)

        # Workspace
        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        self._ws_label = QLabel(str(workspace_root) if workspace_root else "(none)")
        self._ws_label.setStyleSheet(f"color: {FG_DIM};")
        self._ws_label.setWordWrap(True)
        ws_row.addWidget(self._ws_label, 1)
        change_btn = QPushButton("Change...")
        change_btn.clicked.connect(self._on_change_root_clicked)
        ws_row.addWidget(change_btn)
        ws_widget = QWidget()
        ws_widget.setLayout(ws_row)
        form.addRow("Workspace root:", ws_widget)

        # Backups info
        if workspace_root is not None:
            backup_path = workspace_root / ".aura" / "backups"
            backup_text = (
                f"Stored in {backup_path}, never auto-deleted. Manage manually."
            )
        else:
            backup_text = "Stored under <workspace>/.aura/backups/, never auto-deleted."
        backup_label = QLabel(backup_text)
        backup_label.setStyleSheet(f"color: {FG_DIM};")
        backup_label.setWordWrap(True)
        form.addRow("Backups:", backup_label)

        content_layout.addLayout(form)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Start background discovery for planner and worker providers
        self._start_discovery(self._settings.planner_provider)
        self._start_discovery(self._settings.worker_provider)

    # --- Thread cleanup ---

    def _cleanup_thread(self, thread_attr: str, worker_attr: str, wait_ms: int = 15000) -> None:
        thread = getattr(self, thread_attr, None)
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(wait_ms):
                    logger.warning(
                        "Settings dialog thread did not stop cleanly: %s", thread_attr
                    )
                    thread.wait()
        except RuntimeError:
            pass

    def _cleanup_threads(self) -> None:
        self._cleanup_thread("_discovery_thread", "_discovery_worker")

    def done(self, result: int) -> None:  # type: ignore[override]
        self._cleanup_threads()
        super().done(result)

    def closeEvent(self, event):  # type: ignore[override]
        self._cleanup_threads()
        super().closeEvent(event)

    # --- Model discovery ---

    def _start_discovery(self, provider_id: ProviderId) -> None:
        if provider_id in self._discovery_inflight:
            return
        self._discovery_inflight.add(provider_id)

        self._discovery_thread = QThread(self)
        self._discovery_worker = DiscoveryWorker(provider_id)
        self._discovery_worker.moveToThread(self._discovery_thread)
        self._discovery_thread.started.connect(self._discovery_worker.run)
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.finished.connect(self._discovery_thread.quit)
        self._discovery_worker.finished.connect(self._discovery_worker.deleteLater)
        self._discovery_thread.finished.connect(self._discovery_thread.deleteLater)
        self._discovery_thread.start()

    def _on_discovery_finished(
        self,
        provider_id: str,
        models: dict,
        pricing: dict,
        error: str,
    ) -> None:
        self._discovery_inflight.discard(provider_id)
        if error:
            logger.warning("Model discovery failed for %s: %s", provider_id, error)
            return

        cfg = provider_registry.get(provider_id)  # type: ignore[arg-type]
        cfg.models.update(models)
        cfg.pricing.update(pricing)
        save_dynamic_catalog(provider_id, models, pricing)  # type: ignore[arg-type]

        # Repopulate the relevant combo(s), preserving selection
        planner_pid: ProviderId = self._planner_provider_combo.currentData()  # type: ignore[assignment]
        worker_pid: ProviderId = self._worker_provider_combo.currentData()  # type: ignore[assignment]

        if provider_id == planner_pid:
            current = self._planner_model_combo.currentData()
            self._populate_role_models(
                self._planner_model_combo, planner_pid, current, role="planner"
            )

        if provider_id == worker_pid:
            current = self._worker_model_combo.currentData()
            self._populate_role_models(
                self._worker_model_combo, worker_pid, current, role="worker"
            )

    # --- Provider / Model helpers ---

    def _on_planner_provider_changed(self) -> None:
        provider_id: ProviderId = self._planner_provider_combo.currentData()  # type: ignore[assignment]
        self._refresh_api_key_status(provider_id)
        self._api_key_input.setPlaceholderText("Paste API key here...")
        self._populate_role_models(
            self._planner_model_combo,
            provider_id,
            self._settings.default_planner_model,
            role="planner",
        )
        self._start_discovery(provider_id)

    def _on_worker_provider_changed(self) -> None:
        provider_id: ProviderId = self._worker_provider_combo.currentData()  # type: ignore[assignment]
        self._populate_role_models(
            self._worker_model_combo,
            provider_id,
            self._settings.default_worker_model,
            role="worker",
        )
        self._start_discovery(provider_id)

    def _populate_all_role_models(self) -> None:
        planner_pid: ProviderId = self._planner_provider_combo.currentData()  # type: ignore[assignment]
        worker_pid: ProviderId = self._worker_provider_combo.currentData()  # type: ignore[assignment]
        self._populate_role_models(
            self._planner_model_combo,
            planner_pid,
            self._settings.default_planner_model,
            role="planner",
        )
        self._populate_role_models(
            self._worker_model_combo,
            worker_pid,
            self._settings.default_worker_model,
            role="worker",
        )

    def _populate_role_models(
        self,
        combo: QComboBox,
        provider_id: ProviderId,
        current_selection: str,
        role: str = "",
    ) -> None:
        cfg = provider_registry.get(provider_id)
        combo.blockSignals(True)
        combo.clear()

        seen: set[str] = set()
        items: list[tuple[str, str]] = []  # (label, id)

        def add_model(mid: str, label: str = "") -> None:
            if mid in seen:
                return
            seen.add(mid)
            items.append((label or mid, mid))

        # 1. All cfg.models
        for info in cfg.models.values():
            if info.id not in seen:
                add_model(info.id, info.label)

        # 2. Provider default model if missing
        add_model(cfg.default_model)

        # 3. Current selection if missing
        if current_selection:
            add_model(current_selection)

        # 4. For DeepSeek worker, always include DEFAULT_WORKER_MODEL
        if provider_id == "deepseek" and role == "worker":
            from aura.providers.catalog import DEFAULT_WORKER_MODEL

            add_model(DEFAULT_WORKER_MODEL)

        # 5. For DeepSeek planner, always include DEFAULT_PLANNER_MODEL
        if provider_id == "deepseek" and role == "planner":
            from aura.providers.catalog import DEFAULT_PLANNER_MODEL

            add_model(DEFAULT_PLANNER_MODEL)

        for label, mid in items:
            combo.addItem(label, mid)

        # Set selection
        if current_selection:
            idx = combo.findData(current_selection)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                idx = combo.findData(cfg.default_model)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        else:
            idx = combo.findData(cfg.default_model)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        combo.blockSignals(False)

    def _set_combo_to_data(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # --- API Key ---

    def _refresh_api_key_status(self, provider_id: ProviderId) -> None:
        cfg = provider_registry.get(provider_id)
        if os.environ.get(cfg.env_key):
            text = f"{cfg.label} key loaded from {cfg.env_key}."
            color = SUCCESS
        elif get_api_key(provider_id):
            text = f"{cfg.label} key is stored locally."
            color = SUCCESS
        else:
            text = f"No {cfg.label} key found. Set {cfg.env_key} or save one here."
            color = WARN
        self._api_key_status.setText(text)
        self._api_key_status.setStyleSheet(f"color: {color};")

    def _on_save_api_key(self) -> None:
        provider_id: ProviderId = self._planner_provider_combo.currentData()  # type: ignore[assignment]
        key = self._api_key_input.text().strip()
        if not key:
            QMessageBox.information(self, APP_NAME, "Paste an API key before saving.")
            return
        set_api_key(provider_id, key)
        self._api_key_input.clear()
        self._refresh_api_key_status(provider_id)

    def _on_clear_api_key(self) -> None:
        provider_id: ProviderId = self._planner_provider_combo.currentData()  # type: ignore[assignment]
        from aura.key_manager import get_key_manager

        get_key_manager().delete_key(provider_id)
        self._refresh_api_key_status(provider_id)

    # --- Tavily ---

    def _refresh_tavily_status(self) -> None:
        if os.environ.get("TAVILY_API_KEY"):
            text = "Tavily key loaded from TAVILY_API_KEY."
            color = SUCCESS
        elif self._settings.tavily_api_key:
            text = "Tavily key is saved in settings."
            color = SUCCESS
        else:
            text = "No Tavily key saved. Web search will be unavailable."
            color = WARN
        self._tavily_status.setText(text)
        self._tavily_status.setStyleSheet(f"color: {color};")

    def _on_save_tavily_key(self) -> None:
        key = self._tavily_key_input.text().strip()
        if not key:
            QMessageBox.information(self, APP_NAME, "Paste a Tavily key before saving.")
            return
        self._settings.tavily_api_key = key
        self._tavily_key_input.clear()
        save_settings(self.result_settings())
        self._refresh_tavily_status()

    def _on_clear_tavily_key(self) -> None:
        self._settings.tavily_api_key = ""
        save_settings(self.result_settings())
        self._refresh_tavily_status()

    # --- Misc ---

    def _on_change_root_clicked(self) -> None:
        self._on_change_root()
        host = self.parent()
        if host is not None and hasattr(host, "_workspace_root"):
            new_root = getattr(host, "_workspace_root")
            self._ws_label.setText(str(new_root) if new_root else "(none)")

    def _on_pw_toggled(self, _checked: bool) -> None:
        self._refresh_pw_enabled()

    def _refresh_pw_enabled(self) -> None:
        enabled = self._pw_mode_chk.isChecked()
        self._planner_model_combo.setEnabled(enabled)
        self._planner_thinking_combo.setEnabled(enabled)
        self._worker_model_combo.setEnabled(enabled)
        self._worker_thinking_combo.setEnabled(enabled)
        self._worker_temperature_spin.setEnabled(enabled)

    # --- Result ---

    def result_settings(self) -> AppSettings:
        """Read the current widget values and return a fresh AppSettings."""
        result = AppSettings(
            planner_provider=self._planner_provider_combo.currentData(),
            worker_provider=self._worker_provider_combo.currentData(),
            restore_last_conversation=self._restore_chk.isChecked(),
            planner_worker_mode=self._pw_mode_chk.isChecked(),
            show_planner_reasoning=self._settings.show_planner_reasoning,
            default_planner_model=self._planner_model_combo.currentData(),
            default_worker_model=self._worker_model_combo.currentData(),
            default_planner_thinking=self._planner_thinking_combo.currentData(),
            default_worker_thinking=self._worker_thinking_combo.currentData(),
            vision_enabled=self._vision_enabled_chk.isChecked(),
            vision_model=self._vision_model_combo.currentText(),
            vision_endpoint=self._vision_endpoint_combo.currentText(),
            temperature=self._temperature_spin.value(),
            worker_temperature=self._worker_temperature_spin.value(),
            system_prompt=self._single_prompt_edit.toPlainText().strip(),
            planner_system_prompt=self._planner_prompt_edit.toPlainText().strip(),
            worker_system_prompt=self._worker_prompt_edit.toPlainText().strip(),
            auto_commit_enabled=self._auto_commit_chk.isChecked(),
            auto_dispatch=self._auto_dispatch_chk.isChecked(),
            auto_approve=self._auto_approve_chk.isChecked(),
            max_tool_rounds=self._max_rounds_spin.value(),
            sandbox_mode=self._sandbox_combo.currentData(),
            tavily_api_key=self._settings.tavily_api_key,
            terminal_window_geometry=self._settings.terminal_window_geometry,
            first_launch_done=self._settings.first_launch_done,
            onboarding_checklist=dict(self._settings.onboarding_checklist),
            onboarding_version=self._settings.onboarding_version,
            humanizer_enabled=self._settings.humanizer_enabled,
            humanizer_gate_enabled=self._settings.humanizer_gate_enabled,
            humanizer_gate_min_severity=self._settings.humanizer_gate_min_severity,
            humanizer_feature_log=self._settings.humanizer_feature_log,
            humanizer_observe=self._settings.humanizer_observe,
        )
        if not result.planner_worker_mode:
            result.planner_provider = result.planner_provider
            result.default_planner_model = result.default_planner_model
            result.default_planner_thinking = result.default_planner_thinking
        return result

    def accept(self) -> None:  # type: ignore[override]
        new_settings = self.result_settings()
        save_settings(new_settings)
        self._settings = new_settings
        super().accept()
