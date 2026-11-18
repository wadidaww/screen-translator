import tempfile
import unittest
from pathlib import Path

from src.core.config_manager import ConfigManager
from src.core.hotkeys import to_pynput


class HotkeyTests(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual("<ctrl>+<shift>+t", to_pynput("Ctrl+Shift+T"))
        self.assertEqual("<alt>+<f2>", to_pynput("Alt+F2"))


class ConfigTests(unittest.TestCase):
    def tearDown(self):
        ConfigManager.reset_instance()

    def test_defaults_are_not_shared(self):
        ConfigManager.reset_instance()
        with tempfile.TemporaryDirectory() as tmp:
            config = ConfigManager(str(Path(tmp) / "settings.json"))
            config.data["hotkeys"]["toggle_translation"] = "X"
            self.assertEqual(
                "Ctrl+Shift+T", ConfigManager.DEFAULTS["hotkeys"]["toggle_translation"]
            )


if __name__ == "__main__":
    unittest.main()
