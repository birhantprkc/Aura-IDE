"""Red/green diff background highlighting for code editors."""
from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit


def mark_deleted_region(editor: QPlainTextEdit, start: int, end: int) -> None:
    """Highlight a region as deleted (red background)."""
    _set_editor_mark(editor, start, end, QColor(247, 118, 142, 58))


def mark_inserted_region(editor: QPlainTextEdit, start: int, end: int) -> None:
    """Highlight a region as inserted (green background)."""
    _set_editor_mark(editor, start, end, QColor(158, 206, 106, 48))


def _set_editor_mark(
    editor: QPlainTextEdit, start: int, end: int, color: QColor
) -> None:
    if end <= start:
        clear_editor_marks(editor)
        return
    text_len = len(editor.toPlainText())
    cursor = QTextCursor(editor.document())
    cursor.setPosition(max(0, min(start, text_len)))
    cursor.setPosition(max(0, min(end, text_len)), QTextCursor.MoveMode.KeepAnchor)
    selection = QTextEdit.ExtraSelection()
    fmt = QTextCharFormat()
    fmt.setBackground(color)
    selection.format = fmt
    selection.cursor = cursor
    editor.setExtraSelections([selection])


def clear_editor_marks(editor: QPlainTextEdit) -> None:
    """Remove all diff highlights from the editor."""
    editor.setExtraSelections([])
