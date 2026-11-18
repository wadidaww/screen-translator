from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QWidget,
)

from src.core.config_manager import ConfigManager
from src.core.languages import language_name, source_language_codes, target_language_codes

ENGINES = [
    ("hybrid", "Offline first, online fallback"),
    ("offline", "Offline only (Argos)"),
    ("online", "Online only (Google, free)"),
]


def _combo(codes, current: str) -> QComboBox:
    combo = QComboBox()
    for code in codes:
        combo.addItem(f"{language_name(code)} ({code})", code)
    index = combo.findData(current)
    combo.setCurrentIndex(max(0, index))
    return combo


class MainWindow(QMainWindow):
    settings_saved = pyqtSignal()

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.setWindowTitle("OmniView Translator Settings")
        self.resize(420, 360)

        container = QWidget(self)
        layout = QFormLayout(container)

        self.source_lang = _combo(source_language_codes(), self.config.get("source_lang", "auto"))
        self.target_lang = _combo(target_language_codes(), self.config.get("target_lang", "en"))

        self.engine = QComboBox()
        for key, label in ENGINES:
            self.engine.addItem(label, key)
        self.engine.setCurrentIndex(
            max(0, self.engine.findData(self.config.get("translator_engine", "hybrid")))
        )

        self.font_size = QSpinBox()
        self.font_size.setRange(0, 48)
        self.font_size.setSpecialValueText("Auto fit")
        self.font_size.setValue(int(self.config.get("font_size", 0)))

        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.3, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(float(self.config.get("overlay_opacity", 1.0)))

        self.interval = QSpinBox()
        self.interval.setRange(200, 5000)
        self.interval.setSingleStep(100)
        self.interval.setSuffix(" ms")
        self.interval.setValue(int(self.config.get("refresh_interval_ms", 600)))

        self.floating = QCheckBox("Show floating toggle button")
        self.floating.setChecked(bool(self.config.get("show_floating_button", True)))

        hotkeys = self.config.get("hotkeys", {})
        self.hotkey_toggle = QLineEdit(hotkeys.get("toggle_translation", ""))
        self.hotkey_once = QLineEdit(hotkeys.get("translate_once", ""))
        self.hotkey_region = QLineEdit(hotkeys.get("select_region", ""))

        self.tesseract_cmd = QLineEdit(self.config.get("tesseract_cmd", ""))
        self.tesseract_cmd.setPlaceholderText("Auto (tesseract on PATH)")

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)

        layout.addRow("Translate from", self.source_lang)
        layout.addRow("Translate to", self.target_lang)
        layout.addRow("Translator", self.engine)
        layout.addRow("Font size", self.font_size)
        layout.addRow("Overlay opacity", self.opacity)
        layout.addRow("Check screen every", self.interval)
        layout.addRow(self.floating)
        layout.addRow("Hotkey: start/stop", self.hotkey_toggle)
        layout.addRow("Hotkey: translate once", self.hotkey_once)
        layout.addRow("Hotkey: select area", self.hotkey_region)
        layout.addRow("Tesseract path", self.tesseract_cmd)
        layout.addRow(QLabel("Tip: pick the source language for Japanese, Chinese, Korean, etc."))
        layout.addRow(save_btn)
        self.setCentralWidget(container)

    def save_settings(self) -> None:
        engine = self.engine.currentData()
        self.config.set("source_lang", self.source_lang.currentData())
        self.config.set("target_lang", self.target_lang.currentData())
        self.config.set("translator_engine", engine)
        self.config.set("use_online_fallback", engine != "offline")
        self.config.set("font_size", self.font_size.value())
        self.config.set("overlay_opacity", self.opacity.value())
        self.config.set("refresh_interval_ms", self.interval.value())
        self.config.set("show_floating_button", self.floating.isChecked())
        self.config.set("tesseract_cmd", self.tesseract_cmd.text().strip())
        self.config.set(
            "hotkeys",
            {
                "toggle_translation": self.hotkey_toggle.text().strip(),
                "translate_once": self.hotkey_once.text().strip(),
                "select_region": self.hotkey_region.text().strip(),
            },
        )
        self.settings_saved.emit()
        self.hide()
