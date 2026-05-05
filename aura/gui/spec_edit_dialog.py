"""Modal dialog for editing a worker dispatch spec before sending it."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from aura.gui.theme import FG_DIM


class SpecEditDialog(QDialog):
    """Edit goal / files / spec / acceptance before dispatching."""

    def __init__(
        self,
        goal: str,
        files: list[str],
        spec: str,
        acceptance: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit dispatch spec")
        self.setModal(True)
        self.resize(720, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 12)
        outer.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._goal_edit = QLineEdit(goal)
        form.addRow("Goal:", self._goal_edit)

        self._files_edit = QLineEdit(", ".join(files))
        self._files_edit.setPlaceholderText("comma-separated workspace-relative paths")
        form.addRow("Files:", self._files_edit)

        self._spec_edit = QPlainTextEdit(spec)
        self._spec_edit.setMinimumHeight(220)
        form.addRow("Spec:", self._spec_edit)

        self._acceptance_edit = QPlainTextEdit(acceptance)
        self._acceptance_edit.setMinimumHeight(80)
        form.addRow("Acceptance:", self._acceptance_edit)

        outer.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def goal(self) -> str:
        return self._goal_edit.text().strip()

    def files(self) -> list[str]:
        raw = self._files_edit.text().strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]

    def spec(self) -> str:
        return self._spec_edit.toPlainText().strip()

    def acceptance(self) -> str:
        return self._acceptance_edit.toPlainText().strip()
