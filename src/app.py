import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

from PyQt6.QtCore import QPoint, QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from src.core.config_manager import ConfigManager
from src.core.screen_capture import RegionCapture
from src.translation.ocr_engine import OCREngine
from src.translation.translator import TranslatorFactory
from src.ui.main_window import MainWindow
from src.ui.overlay_window import OverlayWindow

try:
    from langdetect import detect
except Exception:  # pragma: no cover
    detect = None


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    activity_handler = RotatingFileHandler("logs/activity.log", maxBytes=2_000_000, backupCount=3)
    activity_handler.setFormatter(formatter)

    error_handler = RotatingFileHandler("logs/error.log", maxBytes=2_000_000, backupCount=3)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(activity_handler)
    root.addHandler(error_handler)


class RegionSelector(QWidget):
    region_selected = pyqtSignal(tuple)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.origin: QPoint | None = None
        self.current: QPoint | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.update()

    def mouseMoveEvent(self, event):
        self.current = event.position().toPoint()
        if self.origin and self.current:
            rect = QRect(self.origin, self.current).normalized()
            QGuiApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
            self.setToolTip(f"x:{rect.x()} y:{rect.y()} w:{rect.width()} h:{rect.height()}")
            self.setToolTipDuration(1000)
            self.setToolTip(self.toolTip())
        self.update()

    def mouseReleaseEvent(self, event):
        if self.origin and self.current:
            rect = QRect(self.origin, self.current).normalized()
            self.region_selected.emit((rect.x(), rect.y(), rect.width(), rect.height()))
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(0.3)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(1.0)
        if self.origin and self.current:
            rect = QRect(self.origin, self.current).normalized()
            painter.setPen(QPen(Qt.GlobalColor.cyan, 2))
            painter.drawRect(rect)


class TranslationWorker(QThread):
    translated = pyqtSignal(str)

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        region = self.config.get("region")
        self.capture = RegionCapture((region["x"], region["y"], region["width"], region["height"]))
        self.ocr = OCREngine()
        self.translator = TranslatorFactory(
            use_online_fallback=bool(self.config.get("use_online_fallback", False))
        ).create()
        self._running = False
        self._last_hash = ""

    def stop(self):
        self._running = False
        self.capture.stop()

    def _looks_like_noise(self, text: str) -> bool:
        return self.ocr._is_noise(text)

    def run(self):
        self._running = True
        self.capture.start()
        while self._running:
            frame = self.capture.grab_frame()
            if frame is None:
                self.msleep(40)
                continue

            result = self.ocr.extract_text(frame)
            text = result["text"].strip()
            del frame

            if not text or self._looks_like_noise(text):
                self.msleep(40)
                continue

            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if text_hash == self._last_hash:
                self.msleep(40)
                continue
            self._last_hash = text_hash

            source = self.config.get("source_lang", "auto")
            target = self.config.get("target_lang", "en")
            if source == "auto" and detect is not None:
                try:
                    source = detect(text)
                except Exception:
                    source = "en"

            try:
                translated = self.translator.translate(text, source, target)
            except Exception:
                logging.getLogger(__name__).exception("Translation failed")
                translated = text
            self.translated.emit(translated)
            self.msleep(40)


class OmniViewApp:
    def __init__(self):
        setup_logging()
        self.qt_app = QApplication(sys.argv)
        self.config = ConfigManager()
        self.overlay = OverlayWindow(opacity=float(self.config.get("overlay_opacity", 0.85)))
        self.settings_window = MainWindow(self.config)
        self.worker: TranslationWorker | None = None
        self.selector: RegionSelector | None = None
        self.tray = self._create_tray()

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(QIcon())
        menu = QMenu()

        select_action = QAction("Select Region")
        select_action.triggered.connect(self.select_region)
        start_action = QAction("Start Translation")
        start_action.triggered.connect(self.start_translation)
        stop_action = QAction("Stop")
        stop_action.triggered.connect(self.stop_translation)
        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.settings_window.show)
        exit_action = QAction("Exit")
        exit_action.triggered.connect(self.exit_app)

        menu.addAction(select_action)
        menu.addAction(start_action)
        menu.addAction(stop_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        tray.setContextMenu(menu)
        tray.show()
        return tray

    def select_region(self):
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self._on_region_selected)
        self.selector.show()

    def _on_region_selected(self, bbox: tuple):
        x, y, w, h = bbox
        self.config.set("region", {"x": x, "y": y, "width": w, "height": h})
        self.overlay.setGeometry(x, y, max(240, w), max(120, h))

    def start_translation(self):
        if self.worker and self.worker.isRunning():
            return
        self.overlay.show()
        self.worker = TranslationWorker(self.config)
        self.worker.translated.connect(self.overlay.set_text)
        self.worker.start()

    def stop_translation(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(1000)
        self.overlay.hide()

    def exit_app(self):
        self.stop_translation()
        self.qt_app.quit()

    def run(self):
        return self.qt_app.exec()


def main() -> int:
    app = OmniViewApp()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
