import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.translation.translator import (
    ArgosOfflineTranslator,
    BaseTranslator,
    CachedTranslator,
    GoogleFreeFallbackTranslator,
    HybridTranslator,
)


class CountingTranslator(BaseTranslator):
    def __init__(self):
        self.calls = []

    def translate(self, text, source_lang, target_lang):
        self.calls.append(text)
        return text.upper()


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

    def test_same_language_is_returned_unchanged(self):
        translator = ArgosOfflineTranslator()
        self.assertEqual("Hello", translator.translate("Hello", "en", "en"))

    def test_cache_avoids_repeat_calls(self):
        inner = CountingTranslator()
        cached = CachedTranslator(inner)
        self.assertEqual(["A", "B"], cached.translate_batch(["a", "b"], "en", "id"))
        self.assertEqual(["A", "C"], cached.translate_batch(["a", "c"], "en", "id"))
        self.assertEqual(["a", "b", "c"], inner.calls)

    def test_hybrid_falls_back(self):
        class Broken(BaseTranslator):
            def translate(self, text, source_lang, target_lang):
                raise RuntimeError("no model")

        hybrid = HybridTranslator(Broken(), CountingTranslator())
        self.assertEqual(["HI"], hybrid.translate_batch(["hi"], "en", "id"))

    def test_google_batch_splits_lines(self):
        google = GoogleFreeFallbackTranslator(sleep_seconds=0)
        with patch.object(
            GoogleFreeFallbackTranslator, "translate", return_value="satu\ndua"
        ) as mocked:
            self.assertEqual(["satu", "dua"], google.translate_batch(["one", "two"], "en", "id"))
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
