"""Small always-on-top round button: click to toggle, right-click for the menu, drag to move."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QMenu, QWidget

from src.ui.overlay_window import exclude_from_capture

SIZE = 48
DRAG_THRESHOLD = 6


def paint_translate_icon(painter: QPainter, rect: QRectF, active: bool, busy: bool = False) -> None:
    """Draw the button face: a globe with no letters, so OCR never picks it up."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    fill = QColor(26, 115, 232) if active else QColor(90, 90, 90)
    painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
    painter.setBrush(fill)
    painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
    inner = rect.adjusted(
        rect.width() * 0.28, rect.height() * 0.28, -rect.width() * 0.28, -rect.height() * 0.28
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255), 2))
    painter.drawEllipse(inner)
    painter.drawEllipse(inner.adjusted(inner.width() * 0.3, 0, -inner.width() * 0.3, 0))
    center = inner.center()
    painter.drawLine(QPointF(inner.left(), center.y()), QPointF(inner.right(), center.y()))
    if busy:
        painter.setPen(QPen(QColor(255, 214, 0), 3))
        painter.drawArc(rect.adjusted(3, 3, -3, -3), 90 * 16, -120 * 16)


class FloatingButton(QWidget):
    toggled = pyqtSignal()

    def __init__(self, menu: QMenu):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(SIZE, SIZE)
        self.setToolTip("Click: start/stop translating\nRight-click: menu\nDrag: move")
        self.menu = menu
        self.active = False
        self.busy = False
        self._press: QPoint | None = None
        self._offset: QPoint | None = None
        self._dragging = False
        self._excluded = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._excluded:
            self._excluded = exclude_from_capture(self)

    def set_state(self, active: bool, busy: bool = False) -> None:
        self.active, self.busy = active, busy
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        paint_translate_icon(painter, QRectF(self.rect()), self.active, self.busy)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._offset = self._press - self.frameGeometry().topLeft()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.popup(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        pos = event.globalPosition().toPoint()
        if (pos - self._press).manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging and self._offset is not None:
            self.move(pos - self._offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragging:
                self.toggled.emit()
            self._press = None
            self._dragging = False
