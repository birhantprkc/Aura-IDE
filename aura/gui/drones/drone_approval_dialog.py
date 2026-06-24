from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from aura.conversation.tools._types import ApprovalDecision, ApprovalRequest
from aura.drones.runner import DroneRunner
from aura.gui.drones.drone_run_card import DroneRunCard

if TYPE_CHECKING:
    from aura.gui.main_window import MainWindow


def show_drone_approval_dialog(
    window: "MainWindow",
    request: ApprovalRequest,
    runner: DroneRunner,
    run_id: str,
    drone_name: str,
    drone_runs: dict[str, dict],
) -> None:
    """Show approval dialog for a write operation requested by a Drone."""
    record = drone_runs.get(run_id) if run_id else None
    run_card = record.get("card") if record else None
    if isinstance(run_card, DroneRunCard):
        run_card.on_status_changed("waiting for approval")
    if run_id and drone_name:
        window._edge_rail.set_drone_run_pip_state(
            run_id, drone_name, "waiting for approval"
        )
        window._drone_reports_window.show_and_focus(run_id)
    approval_id = request.approval_id or None

    # Build the diff text.
    if request.is_new_file:
        diff_text = f"[New file] {request.rel_path}\n\n{request.new_content}"
    else:
        diff_lines = list(
            difflib.unified_diff(
                request.old_content.splitlines(keepends=True),
                request.new_content.splitlines(keepends=True),
                fromfile=request.rel_path,
                tofile=request.rel_path,
            )
        )
        diff_text = "".join(diff_lines) if diff_lines else "(no changes)"

    dialog = QDialog(window._playground)
    dialog.setWindowTitle(f"Drone: {request.tool_name}")
    dialog.resize(600, 400)

    layout = QVBoxLayout(dialog)

    info = QLabel(
        f"<b>Tool:</b> {request.tool_name} | <b>File:</b> {request.rel_path}"
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    diff_view = QPlainTextEdit()
    diff_view.setPlainText(diff_text)
    diff_view.setReadOnly(True)
    layout.addWidget(diff_view, stretch=1)

    button_box = QDialogButtonBox(dialog)
    approve_btn = button_box.addButton(
        "Approve", QDialogButtonBox.ButtonRole.AcceptRole
    )
    reject_btn = button_box.addButton(
        "Reject", QDialogButtonBox.ButtonRole.RejectRole
    )
    approve_all_btn = button_box.addButton(
        "Approve All", QDialogButtonBox.ButtonRole.AcceptRole
    )
    reject_all_btn = button_box.addButton(
        "Reject All", QDialogButtonBox.ButtonRole.RejectRole
    )

    def _accept(action: str) -> None:
        runner.set_approval_result(
            ApprovalDecision(action=action), approval_id=approval_id
        )
        dialog.accept()

    approve_btn.clicked.connect(lambda: _accept("approve"))
    reject_btn.clicked.connect(lambda: _accept("reject"))
    approve_all_btn.clicked.connect(lambda: _accept("approve_all"))
    reject_all_btn.clicked.connect(lambda: _accept("reject_all"))

    layout.addWidget(button_box)

    # Ensure worker thread unblocks even if dialog is closed via X.
    dialog.rejected.connect(
        lambda: runner.set_approval_result(
            ApprovalDecision(action="reject"),
            approval_id=approval_id,
        )
    )

    dialog.exec()
    if (
        run_id
        and drone_name
        and runner.run_state.is_active
        and not runner.run_state.cancel_event.is_set()
    ):
        if isinstance(run_card, DroneRunCard):
            run_card.on_status_changed("running")
        window._edge_rail.set_drone_run_pip_state(
            run_id, drone_name, "running"
        )
