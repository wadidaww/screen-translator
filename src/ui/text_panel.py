"""Window that lists the last translated text so it can be read and copied."""

from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.translation.ocr_engine import TextBlock


def format_blocks(blocks: Sequence[TextBlock], include_original: bool = False) -> str:
    """Plain text for the clipboard: translations only, or original followed by translation."""
    parts = []
    for block in blocks:
        translated = (block.translated or "").strip()
        if not translated:
            continue
        if include_original:
            parts.append(f"{block.text.strip()}\n→ {translated}")
        else:
            parts.append(translated)
    return "\n\n".join(parts)


class TextPanel(QWidget):
    """Read and copy what is currently painted over the screen.

    Click an entry to copy its translation; double-click copies the original text.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Translated text - OmniView")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(460, 520)
        self.blocks: list[TextBlock] = []

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(True)
        self.list.itemClicked.connect(lambda item: self._copy_item(item, original=False))
        self.list.itemDoubleClicked.connect(lambda item: self._copy_item(item, original=True))

        self.status = QLabel("Click a line to copy its translation, double-click for the original.")
        self.status.setWordWrap(True)

        copy_all = QPushButton("Copy translations")
        copy_all.clicked.connect(lambda: self._copy(format_blocks(self.blocks), "Translations"))
        copy_both = QPushButton("Copy original + translation")
        copy_both.clicked.connect(
            lambda: self._copy(format_blocks(self.blocks, include_original=True), "Both")
        )
        buttons = QHBoxLayout()
        buttons.addWidget(copy_all)
        buttons.addWidget(copy_both)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

    def set_blocks(self, blocks: Sequence[TextBlock]) -> None:
        self.blocks = [b for b in blocks if (b.translated or "").strip()]
        self.list.clear()
        if not self.blocks:
            self.list.addItem("Nothing translated yet. Start translating first.")
            return
        for index, block in enumerate(self.blocks):
            item = QListWidgetItem(f"{block.translated.strip()}\n    {block.text.strip()}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(block.text)
            self.list.addItem(item)

    def _copy_item(self, item: QListWidgetItem, original: bool) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        block = self.blocks[index]
        self._copy(
            block.text if original else block.translated, "Original" if original else "Translation"
        )

    def _copy(self, text: str, what: str) -> None:
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.status.setText(f"{what} copied to the clipboard.")
