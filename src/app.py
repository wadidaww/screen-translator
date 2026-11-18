"""OmniView Translator desktop app: tray icon, floating button, hotkeys and overlay."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import List, Optional, Tuple

from PyQt6.QtCore import QMetaObject, QObject, QRect, QRectF, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from src.core.config_manager import ConfigManager, default_config_dir
from src.core.hotkeys import GlobalHotkeys
from src.core.pipeline import LiveLoop, TranslationPipeline
from src.core.screen_capture import ScreenGrabber
from src.translation.ocr_engine import OCREngine, TextBlock
from src.translation.translator import TranslatorFactory
from src.ui.floating_button import FloatingButton, paint_translate_icon
from src.ui.main_window import MainWindow
from src.ui.overlay_window import OverlayItem, OverlayWindow
from src.ui.region_selector import RegionSelector
from src.ui.text_panel import TextPanel

LOGGER = logging.getLogger(__name__)
LogicalRect = Tuple[int, int, int, int]


def setup_logging() -> None:
    log_max_bytes = 2_000_000
    log_dir = default_config_dir() / "logs"
    os.makedirs(log_dir, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    activity_handler = RotatingFileHandler(
        log_dir / "activity.log", maxBytes=log_max_bytes, backupCount=3, encoding="utf-8"
    )
    activity_handler.setFormatter(formatter)
    error_handler = RotatingFileHandler(
        log_dir / "error.log", maxBytes=log_max_bytes, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(activity_handler)
    root.addHandler(error_handler)
    if sys.stderr is not None:  # windowed builds have no console
        root.addHandler(console)


def make_icon(active: bool) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_translate_icon(painter, QRectF(0, 0, 64, 64), active)
    painter.end()
    return QIcon(pixmap)


def physical_bbox(rect: LogicalRect) -> Tuple[int, int, int, int]:
    """Convert a logical (Qt) rectangle to the physical pixels mss expects."""
    x, y, w, h = rect
    if sys.platform == "darwin":  # mss works in points on macOS
        return x, y, w, h
    screen = QGuiApplication.screenAt(QRect(x, y, w, h).center()) or QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio()
    origin = screen.geometry().topLeft()
    px = origin.x() + round((x - origin.x()) * dpr)
    py = origin.y() + round((y - origin.y()) * dpr)
    return px, py, max(1, round(w * dpr)), max(1, round(h * dpr))


class TranslationWorker(QThread):
    """Runs the LiveLoop on a background thread and talks to the overlay via signals."""

    blocks_ready = pyqtSignal(list, float)  # blocks, frame->logical scale
    status = pyqtSignal(str)
    busy = pyqtSignal(bool)

    def __init__(
        self, config: ConfigManager, region: LogicalRect, overlay: OverlayWindow, live: bool = True
    ):
        super().__init__()
        self.config = config
        self.region = region
        self.overlay = overlay
        self.live = live
        self.loop: Optional[LiveLoop] = None
        self._scale = 1.0
        self.bbox = physical_bbox(region)

    def _clear_overlay(self) -> None:
        QMetaObject.invokeMethod(
            self.overlay, "clear_now", Qt.ConnectionType.BlockingQueuedConnection
        )
        if not self.overlay.excluded_from_capture:
            self.msleep(80)  # let the compositor drop the old frame

    def stop(self) -> None:
        if self.loop:
            self.loop.stop()

    def run(self) -> None:
        source = self.config.get("source_lang", "auto")
        target = self.config.get("target_lang", "en")
        engine = self.config.get("translator_engine") or (
            "hybrid" if self.config.get("use_online_fallback") else "offline"
        )
        ocr = OCREngine(source_lang=source, tesseract_cmd=self.config.get("tesseract_cmd") or None)
        if not OCREngine.tesseract_available():
            self.status.emit(
                "Tesseract OCR was not found. Install it and/or set its path in Settings."
            )
            return
        translator = TranslatorFactory(engine=engine).create()
        pipeline = TranslationPipeline(ocr, translator, source, target)
        pipeline.online_auto = engine == "online"

        grabber = ScreenGrabber()
        bbox = self.bbox

        def grab():
            frame = grabber.grab(bbox)
            self._scale = frame.shape[1] / max(1, self.region[2])
            return frame

        def show(blocks: List[TextBlock]) -> None:
            self.blocks_ready.emit(blocks, self._scale)

        self.loop = LiveLoop(
            grab=grab,
            pipeline=pipeline,
            show=show,
            clear=self._clear_overlay,
            overlay_excluded=lambda: self.overlay.excluded_from_capture,
            live=self.live,
            interval=int(self.config.get("refresh_interval_ms", 600)) / 1000.0,
            peek_interval=int(self.config.get("peek_interval_ms", 2500)) / 1000.0,
            sleep=lambda s: self.msleep(int(s * 1000)),
            on_busy=self.busy.emit,
        )
        try:
            self.loop.run()
        finally:
            grabber.close()


class HotkeyBridge(QObject):
    """Moves pynput callbacks (background thread) onto the Qt thread."""

    toggle = pyqtSignal()
    once = pyqtSignal()
    region = pyqtSignal()


class OmniViewApp:
    def __init__(self):
        setup_logging()
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setApplicationName("OmniView Translator")
        self.config = ConfigManager()
        self.overlay = OverlayWindow(
            opacity=float(self.config.get("overlay_opacity", 1.0)),
            font_size=int(self.config.get("font_size", 0)),
        )
        self.settings_window = MainWindow(self.config)
        self.settings_window.settings_saved.connect(self.apply_settings)
        self.worker: Optional[TranslationWorker] = None
        self.selector: Optional[RegionSelector] = None
        self.text_panel: Optional[TextPanel] = None
        self.last_blocks: List[TextBlock] = []

        self.menu = self._create_menu()
        self.tray = QSystemTrayIcon(make_icon(False))
        self.tray.setToolTip("OmniView Translator")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.floating = FloatingButton(self.menu)
        self.floating.toggled.connect(self.toggle_translation)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.floating.move(screen.right() - 80, screen.top() + screen.height() // 3)
        if self.config.get("show_floating_button", True):
            self.floating.show()

        self.bridge = HotkeyBridge()
        self.bridge.toggle.connect(self.toggle_translation)
        self.bridge.once.connect(self.translate_once)
        self.bridge.region.connect(self.select_region)
        self.hotkeys = GlobalHotkeys()
        self._register_hotkeys()

        if not OCREngine.tesseract_available():
            self.notify("Tesseract OCR was not found. See README for install steps.")

    # ------------------------------------------------------------- menu/tray
    def _create_menu(self) -> QMenu:
        menu = QMenu()
        self.toggle_action = QAction("Start translating", menu)
        self.toggle_action.triggered.connect(self.toggle_translation)
        self.once_action = QAction("Translate once", menu)
        self.once_action.triggered.connect(self.translate_once)
        self.region_action = QAction("Select area...", menu)
        self.region_action.triggered.connect(self.select_region)
        self.fullscreen_action = QAction("Use whole screen", menu)
        self.fullscreen_action.triggered.connect(self.use_full_screen)
        self.text_action = QAction("Show translated text...", menu)
        self.text_action.triggered.connect(self.show_text_panel)
        self.button_action = QAction("Show floating button", menu, checkable=True)
        self.button_action.setChecked(bool(self.config.get("show_floating_button", True)))
        self.button_action.toggled.connect(self._set_floating_visible)
        self.settings_action = QAction("Settings...", menu)
        self.settings_action.triggered.connect(self.show_settings)
        self.exit_action = QAction("Exit", menu)
        self.exit_action.triggered.connect(self.exit_app)
        for action in (self.toggle_action, self.once_action, self.text_action):
            menu.addAction(action)
        menu.addSeparator()
        for action in (
            self.region_action,
            self.fullscreen_action,
            self.button_action,
            self.settings_action,
        ):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.exit_action)
        return menu

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_translation()

    def _set_floating_visible(self, visible: bool) -> None:
        self.config.set("show_floating_button", visible)
        self.floating.setVisible(visible)

    def _register_hotkeys(self) -> None:
        keys = self.config.get("hotkeys", {})
        bindings = {
            keys.get("toggle_translation", ""): self.bridge.toggle.emit,
            keys.get("translate_once", ""): self.bridge.once.emit,
            keys.get("select_region", ""): self.bridge.region.emit,
        }
        bindings.pop("", None)
        if not self.hotkeys.start(bindings):
            LOGGER.info("Global hotkeys disabled (pynput missing or unsupported session)")

    def notify(self, message: str) -> None:
        LOGGER.warning(message)
        if QSystemTrayIcon.supportsMessages() and self.tray.isVisible():
            self.tray.showMessage("OmniView Translator", message)
        else:
            QMessageBox.information(None, "OmniView Translator", message)

    def show_text_panel(self) -> None:
        if self.text_panel is None:
            self.text_panel = TextPanel()
        self.text_panel.set_blocks(self.last_blocks)
        self.text_panel.show()
        self.text_panel.raise_()
        self.text_panel.activateWindow()

    def show_settings(self) -> None:
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def apply_settings(self) -> None:
        self.overlay.opacity = float(self.config.get("overlay_opacity", 1.0))
        self.overlay.font_size = int(self.config.get("font_size", 0))
        self.floating.setVisible(bool(self.config.get("show_floating_button", True)))
        self.button_action.setChecked(self.floating.isVisible())
        self._register_hotkeys()
        if self.is_running():
            live = self.worker.live if self.worker else True
            self.stop_translation()
            self.start_translation(live=live)

    # ---------------------------------------------------------------- region
    def current_region(self) -> LogicalRect:
        region = self.config.get("region")
        if isinstance(region, dict) and region.get("width", 0) > 0:
            return (int(region["x"]), int(region["y"]), int(region["width"]), int(region["height"]))
        geometry = QGuiApplication.primaryScreen().geometry()
        return geometry.x(), geometry.y(), geometry.width(), geometry.height()

    def select_region(self) -> None:
        self.stop_translation()
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self._on_region_selected)
        self.selector.show()
        self.selector.activateWindow()

    def _on_region_selected(self, bbox: tuple) -> None:
        x, y, w, h = bbox
        self.config.set("region", {"x": x, "y": y, "width": w, "height": h})
        self.start_translation()

    def use_full_screen(self) -> None:
        self.config.set("region", None)
        if self.is_running():
            self.stop_translation()
            self.start_translation()

    # ------------------------------------------------------------ translating
    def is_running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def toggle_translation(self) -> None:
        if self.is_running():
            self.stop_translation()
        else:
            self.start_translation()

    def translate_once(self) -> None:
        if self.is_running():
            self.stop_translation()
            return
        self.start_translation(live=False)

    def start_translation(self, live: bool = True) -> None:
        if self.is_running():
            return
        region = self.current_region()
        self.overlay.clear_now()
        self.overlay.setGeometry(*region)
        self.overlay.show()
        self.worker = TranslationWorker(self.config, region, self.overlay, live=live)
        self.worker.blocks_ready.connect(self._show_blocks)
        self.worker.status.connect(self.notify)
        self.worker.busy.connect(self._on_busy)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self._set_active(True)

    def stop_translation(self) -> None:
        worker = self.worker
        if worker:
            worker.stop()
            # Worker may be blocked waiting on the GUI thread; keep the event loop alive.
            while worker.isRunning():
                worker.wait(50)
                self.qt_app.processEvents()
        self.worker = None
        self.overlay.clear_now()
        self.overlay.hide()
        self._set_active(False)

    def _on_worker_finished(self) -> None:
        if self.worker is not None and not self.worker.isRunning():
            if not self.worker.live:  # one-shot finished by itself
                self.stop_translation()

    def _set_active(self, active: bool) -> None:
        self.toggle_action.setText("Stop translating" if active else "Start translating")
        self.tray.setIcon(make_icon(active))
        self.floating.set_state(active)

    def _on_busy(self, busy: bool) -> None:
        running = self.is_running()
        self.floating.set_state(running, busy and running)

    def _show_blocks(self, blocks: List[TextBlock], scale: float) -> None:
        if not self.is_running():
            return
        scale = scale or 1.0
        self.last_blocks = list(blocks)
        if self.text_panel is not None and self.text_panel.isVisible():
            self.text_panel.set_blocks(self.last_blocks)
        items = []
        for block in blocks:
            x, y, w, h = block.box
            rect = QRect(
                round(x / scale),
                round(y / scale),
                max(8, round(w / scale)),
                max(8, round(h / scale)),
            )
            items.append(
                OverlayItem(
                    rect, block.translated, QColor(*block.background), QColor(*block.foreground)
                )
            )
        self.overlay.set_items(items)

    def exit_app(self) -> None:
        self.stop_translation()
        self.hotkeys.stop()
        self.tray.hide()
        self.qt_app.quit()

    def run(self) -> int:
        return self.qt_app.exec()


def _report(message: str) -> None:
    # Windowed (no console) builds have no stdout; log to the activity log as well.
    LOGGER.info(message)
    if sys.stdout is not None:
        print(message)


def self_test() -> int:
    """Headless check used by the packaged build: can we load everything and read text?"""
    import cv2
    import numpy as np

    from src.translation.translator import TranslatorFactory

    TranslatorFactory(engine="hybrid").create()
    if not OCREngine.tesseract_available():
        _report("self-test: tesseract not found")
        return 2
    image = np.full((120, 640, 3), 255, dtype=np.uint8)
    cv2.putText(image, "HELLO WORLD", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    text = " ".join(block.text for block in OCREngine(source_lang="en").extract_blocks(image))
    _report(f"self-test: OCR read {text!r}")
    return 0 if "HELLO" in text.upper() else 3


def main() -> int:
    if "--self-test" in sys.argv:
        setup_logging()
        return self_test()
    app = OmniViewApp()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
