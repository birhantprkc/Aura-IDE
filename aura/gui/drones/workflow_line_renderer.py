from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene

from aura.gui.drones.chain_node_item import NODE_HEIGHT, NODE_WIDTH
from aura.gui.drones.mission_core_item import MISSION_CORE_WIDTH


class _WorkflowLineSegment(QGraphicsPathItem):
    """A single cubic-Bezier segment of the workflow path on the chain canvas."""

    def __init__(
        self,
        start_pos: QPointF,
        end_pos: QPointF,
        is_return: bool = False,
    ) -> None:
        super().__init__()
        self._start_pos = start_pos
        self._end_pos = end_pos
        self._is_return = is_return
        self._loop_enabled = False

        self.setZValue(0)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._build_bezier()

    def _build_bezier(self) -> None:
        dx = self._end_pos.x() - self._start_pos.x()
        offset = max(40.0, dx * 0.5)

        path = QPainterPath()
        path.moveTo(self._start_pos)
        path.cubicTo(
            QPointF(self._start_pos.x() + offset, self._start_pos.y()),
            QPointF(self._end_pos.x() - offset, self._end_pos.y()),
            self._end_pos,
        )
        self.setPath(path)

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ) -> None:
        if not self.path():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_bright = not self._is_return or self._loop_enabled

        # Glow underlay — two passes
        glow_color = QColor("#7aa2f7") if is_bright else QColor("#6e7382")

        glow1_color = QColor(glow_color)
        glow1_color.setAlpha(10 if is_bright else 6)
        painter.setPen(QPen(glow1_color, 6))
        painter.drawPath(self.path())

        glow2_color = QColor(glow_color)
        glow2_color.setAlpha(22 if is_bright else 12)
        painter.setPen(QPen(glow2_color, 3))
        painter.drawPath(self.path())

        # Main stroke
        if is_bright:
            gradient = QLinearGradient(self._start_pos, self._end_pos)
            gradient.setColorAt(0.0, QColor("#7aa2f7"))
            gradient.setColorAt(1.0, QColor("#9d7cd8"))
            pen = QPen()
            pen.setBrush(gradient)
            pen.setWidthF(2.0)
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        else:
            pen = QPen(QColor("#6e7382"), 2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.setPen(pen)
        painter.drawPath(self.path())

    def refresh(self, start_pos: QPointF, end_pos: QPointF) -> None:
        self._start_pos = start_pos
        self._end_pos = end_pos
        self._build_bezier()
        self.update()

    def set_loop_enabled(self, enabled: bool) -> None:
        self._loop_enabled = enabled
        self.update()


class WorkflowLineRenderer:
    """Owns the visual workflow path segments on the chain canvas.

    The renderer creates and manages ``_WorkflowLineSegment`` items that
    draw cubic-Bezier curves between the mission core and ordered drone
    nodes.
    """

    def __init__(self, scene: QGraphicsScene) -> None:
        self._scene = scene
        self._segments: list[_WorkflowLineSegment] = []
        self._mission_core = None
        self._nodes: list = []
        self._loop_enabled = False

    def set_context(self, mission_core, nodes: list, loop_enabled: bool) -> None:
        """Record current workflow context without rebuilding."""
        self._mission_core = mission_core
        self._nodes = list(nodes)
        self._loop_enabled = loop_enabled

    def rebuild(self) -> None:
        """Clear existing segments and create new ones from current context."""
        self.clear()
        if not self._mission_core or not self._nodes:
            return

        mc = self._mission_core
        nodes = self._nodes

        # Forward segments: MC → n0, n0 → n1, …
        mc_right = mc.pos() + QPointF(MISSION_CORE_WIDTH / 2, 0)

        for i, node in enumerate(nodes):
            if i == 0:
                start = mc_right
            else:
                prev = nodes[i - 1]
                start = prev.pos() + QPointF(NODE_WIDTH, NODE_HEIGHT / 2)

            end = node.pos() + QPointF(0, NODE_HEIGHT / 2)
            seg = _WorkflowLineSegment(start, end, is_return=False)
            self._segments.append(seg)
            self._scene.addItem(seg)

        # Return segment: last node output → MC left edge center
        last = nodes[-1]
        ret_start = last.pos() + QPointF(NODE_WIDTH, NODE_HEIGHT / 2)
        mc_left = mc.pos() - QPointF(MISSION_CORE_WIDTH / 2, 0)
        ret_seg = _WorkflowLineSegment(ret_start, mc_left, is_return=True)
        ret_seg.set_loop_enabled(self._loop_enabled)
        self._segments.append(ret_seg)
        self._scene.addItem(ret_seg)

    def clear(self) -> None:
        """Remove all segments from the scene and clear the list."""
        for seg in self._segments:
            self._scene.removeItem(seg)
        self._segments.clear()

    def update_positions(self) -> None:
        """Fast path for node movement — refreshes segment endpoints in place.

        Falls back to :meth:`rebuild` if the segment count is out of sync.
        """
        if not self._mission_core or not self._nodes:
            return

        expected = len(self._nodes) + 1  # one forward per node + one return
        if len(self._segments) != expected:
            self.rebuild()
            return

        mc = self._mission_core
        nodes = self._nodes
        mc_right = mc.pos() + QPointF(MISSION_CORE_WIDTH / 2, 0)

        for i, node in enumerate(nodes):
            start = mc_right if i == 0 else nodes[i - 1].pos() + QPointF(
                NODE_WIDTH, NODE_HEIGHT / 2,
            )
            end = node.pos() + QPointF(0, NODE_HEIGHT / 2)
            self._segments[i].refresh(start, end)

        # Return segment (last index)
        last = nodes[-1]
        ret_start = last.pos() + QPointF(NODE_WIDTH, NODE_HEIGHT / 2)
        mc_left = mc.pos() - QPointF(MISSION_CORE_WIDTH / 2, 0)
        self._segments[-1].refresh(ret_start, mc_left)

    def update_loop_state(self, loop_enabled: bool) -> None:
        """Toggle loop appearance on all existing return segments."""
        self._loop_enabled = loop_enabled
        for seg in self._segments:
            seg.set_loop_enabled(loop_enabled)
