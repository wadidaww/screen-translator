from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

MIN_REGION = 20


class RegionSelector(QWidget):
    """Full-screen dimmed layer; drag a rectangle to choose what to translate. Esc cancels."""

    region_selected = pyqtSignal(tuple)  # global logical (x, y, w, h)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        geometry = QRect()
        for screen in QGuiApplication.screens():
            geometry = geometry.united(screen.geometry())
        self.setGeometry(geometry)
        self.origin: QPoint | None = None
        self.current: QPoint | None = None

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.update()
        else:
            self.close()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self.origin is not None:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self.origin is not None and self.current is not None:
            rect = QRect(self.origin, self.current).normalized()
            if rect.width() >= MIN_REGION and rect.height() >= MIN_REGION:
                top_left = self.mapToGlobal(rect.topLeft())
                self.region_selected.emit((top_left.x(), top_left.y(), rect.width(), rect.height()))
        self.close()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self.origin is not None and self.current is not None:
            rect = QRect(self.origin, self.current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(0, 200, 255), 2))
            painter.drawRect(rect)
            painter.drawText(rect.bottomLeft() + QPoint(4, 16), f"{rect.width()} x {rect.height()}")
        else:
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter),
                "Drag to select the area to translate  (Esc to cancel)",
            )
        painter.end()
