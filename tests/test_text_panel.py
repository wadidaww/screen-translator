import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.translation.ocr_engine import TextBlock  # noqa: E402

try:
    from PyQt6.QtWidgets import QApplication

    from src.ui.text_panel import TextPanel, format_blocks
except ImportError:  # pragma: no cover - Qt missing in some environments
    QApplication = None


@unittest.skipIf(QApplication is None, "PyQt6 not available")
class TextPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.blocks = [
            TextBlock(text="Bonjour", box=(0, 0, 10, 10), translated="Hello"),
            TextBlock(text="skip me", box=(0, 0, 10, 10), translated=""),
            TextBlock(text="Merci", box=(0, 0, 10, 10), translated="Thanks"),
        ]

    def test_format_translations_only(self):
        self.assertEqual(format_blocks(self.blocks), "Hello\n\nThanks")

    def test_format_with_original(self):
        self.assertEqual(
            format_blocks(self.blocks, include_original=True),
            "Bonjour\n→ Hello\n\nMerci\n→ Thanks",
        )

    def test_panel_lists_and_copies(self):
        panel = TextPanel()
        panel.set_blocks(self.blocks)
        self.assertEqual(panel.list.count(), 2)
        panel._copy_item(panel.list.item(1), original=True)
        self.assertEqual(self.app.clipboard().text(), "Merci")

    def test_empty_panel_shows_hint(self):
        panel = TextPanel()
        panel.set_blocks([])
        self.assertEqual(panel.list.count(), 1)
        panel._copy_item(panel.list.item(0), original=False)  # no crash


if __name__ == "__main__":
    unittest.main()
