import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.translation.translator import ArgosOfflineTranslator


class TranslationTests(unittest.TestCase):
    def test_offline_translation_without_network(self):
        class DummyTranslation:
            def translate(self, text):
                return "Buenos días" if text == "Good morning" else text

        class DummyLang:
            def __init__(self, code):
                self.code = code

            def get_translation(self, target):
                if self.code == "en" and target.code == "es":
                    return DummyTranslation()
                raise ValueError("missing")

        dummy_module = SimpleNamespace(
            get_installed_languages=lambda: [DummyLang("en"), DummyLang("es")]
        )

        with (
            patch("src.translation.translator.argos_translate", dummy_module),
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("Network should not be used"),
            ),
        ):
            translator = ArgosOfflineTranslator()
            result = translator.translate("Good morning", "en", "es")

        self.assertEqual("Buenos días", result)


if __name__ == "__main__":
    unittest.main()
