import logging
import time
from dataclasses import dataclass

from src.translation.model_manager import ArgosModelManager

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None

try:
    import argostranslate.translate as argos_translate
except ImportError:  # pragma: no cover
    argos_translate = None

LOGGER = logging.getLogger(__name__)
DEFAULT_RATE_LIMIT_SLEEP = 0.5


class BaseTranslator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:  # pragma: no cover
        raise NotImplementedError


class ArgosOfflineTranslator(BaseTranslator):
    def __init__(self, model_manager: ArgosModelManager | None = None):
        self.model_manager = model_manager or ArgosModelManager()

    def _find_translation(self, source_lang: str, target_lang: str):
        if argos_translate is None:
            return None
        installed = argos_translate.get_installed_languages()
        source = next((l for l in installed if l.code == source_lang), None)
        target = next((l for l in installed if l.code == target_lang), None)
        if not source or not target:
            return None
        return source.get_translation(target)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text.strip():
            return ""

        translation = self._find_translation(source_lang, target_lang)
        if translation is None:
            if not self.model_manager.ensure_model_installed(source_lang, target_lang):
                raise RuntimeError(f"Unable to install Argos model {source_lang}->{target_lang}")
            translation = self._find_translation(source_lang, target_lang)
            if translation is None:
                raise RuntimeError(f"Argos model not available after install for {source_lang}->{target_lang}")

        try:
            return translation.translate(text)
        except Exception:
            LOGGER.exception("Argos translation failed, retrying model install")
            if self.model_manager.ensure_model_installed(source_lang, target_lang):
                translation = self._find_translation(source_lang, target_lang)
                if translation:
                    return translation.translate(text)
            raise


class GoogleFreeFallbackTranslator(BaseTranslator):
    def __init__(self, sleep_seconds: float = DEFAULT_RATE_LIMIT_SLEEP):
        self.sleep_seconds = sleep_seconds

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if GoogleTranslator is None:
            raise RuntimeError("deep-translator is not installed")
        if not text.strip():
            return ""
        time.sleep(self.sleep_seconds)
        try:
            src = source_lang if source_lang != "auto" else "auto"
            return GoogleTranslator(source=src, target=target_lang).translate(text)
        except Exception:
            LOGGER.exception("Online fallback translation failed")
            raise


@dataclass
class TranslatorFactory:
    use_online_fallback: bool = False
    model_manager: ArgosModelManager | None = None

    def create(self) -> BaseTranslator:
        if self.use_online_fallback:
            return HybridTranslator(
                primary=ArgosOfflineTranslator(self.model_manager),
                secondary=GoogleFreeFallbackTranslator(),
            )
        return ArgosOfflineTranslator(self.model_manager)


class HybridTranslator(BaseTranslator):
    def __init__(self, primary: BaseTranslator, secondary: BaseTranslator):
        self.primary = primary
        self.secondary = secondary

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            return self.primary.translate(text, source_lang, target_lang)
        except Exception:
            LOGGER.warning("Primary translator failed, trying online fallback")
            return self.secondary.translate(text, source_lang, target_lang)
