from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QWidget,
)

from src.core.config_manager import ConfigManager


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.setWindowTitle("OmniView Translator Settings")
        self.resize(360, 220)

        container = QWidget(self)
        layout = QFormLayout(container)

        self.source_lang = QComboBox()
        self.source_lang.addItems(["auto", "en", "es", "fr", "de", "ja", "zh"])
        self.source_lang.setCurrentText(self.config.get("source_lang", "auto"))

        self.target_lang = QComboBox()
        self.target_lang.addItems(["en", "es", "fr", "de", "ja", "zh"])
        self.target_lang.setCurrentText(self.config.get("target_lang", "en"))

        self.font_size = QSpinBox()
        self.font_size.setRange(10, 48)
        self.font_size.setValue(int(self.config.get("font_size", 14)))

        self.online_toggle = QCheckBox("Use online fallback")
        self.online_toggle.setChecked(bool(self.config.get("use_online_fallback", False)))

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)

        layout.addRow("Source language", self.source_lang)
        layout.addRow("Target language", self.target_lang)
        layout.addRow("Font size", self.font_size)
        layout.addRow(self.online_toggle)
        layout.addRow(save_btn)
        self.setCentralWidget(container)

    def save_settings(self) -> None:
        self.config.set("source_lang", self.source_lang.currentText())
        self.config.set("target_lang", self.target_lang.currentText())
        self.config.set("font_size", self.font_size.value())
        self.config.set("use_online_fallback", self.online_toggle.isChecked())
