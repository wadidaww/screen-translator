from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None


class OverlayWindow(QWidget):
    def __init__(self, opacity: float = 0.85):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_start: QPoint | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if QWebEngineView is not None:
            self.web = QWebEngineView(self)
            self.web.setHtml(self._base_html(""))
            layout.addWidget(self.web)
        else:
            self.web = None

        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        self.setGraphicsEffect(effect)
        self.resize(480, 180)

    def _base_html(self, text: str) -> str:
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped = escaped.replace("\n", "<br>")
        return f"""
        <html>
          <head>
            <style>
              body {{ margin: 0; padding: 12px; background: rgba(20,20,20,0.45); backdrop-filter: blur(10px); }}
              #content {{ color: white; font-size: 18px; text-shadow: 1px 1px 2px black; line-height: 1.4; }}
            </style>
          </head>
          <body>
            <div id=\"content\">{escaped}</div>
          </body>
        </html>
        """

    def set_text(self, text: str) -> None:
        if self.web is not None:
            self.web.setHtml(self._base_html(text))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
