import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional

from src.core.languages import detect_language
from src.translation.model_manager import ArgosModelManager

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover - optional dependency
    GoogleTranslator = None

try:
    import argostranslate.translate as argos_translate
except ImportError:  # pragma: no cover - optional dependency
    argos_translate = None

LOGGER = logging.getLogger(__name__)
DEFAULT_RATE_LIMIT_SLEEP = 0.2
CACHE_SIZE = 2000
BATCH_SEPARATOR = "\n"

# Google uses a few codes that differ from ours.
GOOGLE_CODES = {"zh": "zh-CN", "zt": "zh-TW", "he": "iw"}


class BaseTranslator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        return [self.translate(t, source_lang, target_lang) for t in texts]


class ArgosOfflineTranslator(BaseTranslator):
    def __init__(self, model_manager: ArgosModelManager | None = None):
        self.model_manager = model_manager or ArgosModelManager()

    def _find_translation(self, source_lang: str, target_lang: str):
        if argos_translate is None:
            return None
        installed = argos_translate.get_installed_languages()
        source = next((lang for lang in installed if lang.code == source_lang), None)
        target = next((lang for lang in installed if lang.code == target_lang), None)
        if not source or not target:
            return None
        try:
            return source.get_translation(target)
        except Exception:
            return None

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text.strip():
            return ""
        if source_lang == "auto":
            source_lang = detect_language(text)
        if source_lang == target_lang:
            return text

        translation = self._find_translation(source_lang, target_lang)
        if translation is None:
            if not self.model_manager.ensure_model_installed(source_lang, target_lang):
                raise RuntimeError(f"Unable to install Argos model {source_lang}->{target_lang}")
            translation = self._find_translation(source_lang, target_lang)
            if translation is None:
                raise RuntimeError(
                    f"Argos model not available after install for {source_lang}->{target_lang}"
                )
        return translation.translate(text)


class GoogleFreeFallbackTranslator(BaseTranslator):
    def __init__(self, sleep_seconds: float = DEFAULT_RATE_LIMIT_SLEEP):
        self.sleep_seconds = sleep_seconds

    @staticmethod
    def _code(code: str) -> str:
        return GOOGLE_CODES.get(code, code)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if GoogleTranslator is None:
            raise RuntimeError("deep-translator is not installed")
        if not text.strip():
            return ""
        time.sleep(self.sleep_seconds)
        result = GoogleTranslator(
            source=self._code(source_lang), target=self._code(target_lang)
        ).translate(text)
        return result or text

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Send all paragraphs in one request; fall back to one-by-one if lines shift."""
        if not texts:
            return []
        joined = BATCH_SEPARATOR.join(t.replace("\n", " ") for t in texts)
        if len(joined) < 4500:
            try:
                parts = self.translate(joined, source_lang, target_lang).split(BATCH_SEPARATOR)
                if len(parts) == len(texts):
                    return [p.strip() for p in parts]
            except Exception:
                LOGGER.exception("Batch translation failed, retrying one by one")
        return [self.translate(t, source_lang, target_lang) for t in texts]


class HybridTranslator(BaseTranslator):
    def __init__(self, primary: BaseTranslator, secondary: BaseTranslator):
        self.primary = primary
        self.secondary = secondary

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            return self.primary.translate(text, source_lang, target_lang)
        except Exception:
            LOGGER.warning("Primary translator failed, trying fallback")
            return self.secondary.translate(text, source_lang, target_lang)

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        try:
            return self.primary.translate_batch(texts, source_lang, target_lang)
        except Exception:
            LOGGER.warning("Primary translator failed, trying fallback")
            return self.secondary.translate_batch(texts, source_lang, target_lang)


class CachedTranslator(BaseTranslator):
    """LRU cache in front of any translator, so unchanged text is never re-sent."""

    def __init__(self, inner: BaseTranslator, size: int = CACHE_SIZE):
        self.inner = inner
        self.size = size
        self._cache: "OrderedDict[tuple, str]" = OrderedDict()
        self._lock = threading.Lock()

    def _get(self, key: tuple) -> Optional[str]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _put(self, key: tuple, value: str) -> None:
        with self._lock:
            self._cache[key] = value
            while len(self._cache) > self.size:
                self._cache.popitem(last=False)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        return self.translate_batch([text], source_lang, target_lang)[0]

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        results: List[Optional[str]] = [self._get((t, source_lang, target_lang)) for t in texts]
        missing = [i for i, r in enumerate(results) if r is None]
        if missing:
            fresh = self.inner.translate_batch(
                [texts[i] for i in missing], source_lang, target_lang
            )
            for i, value in zip(missing, fresh):
                results[i] = value
                self._put((texts[i], source_lang, target_lang), value)
        return [r or "" for r in results]


@dataclass
class TranslatorFactory:
    """Builds the translator chain.

    ``engine`` is one of ``offline`` (Argos only), ``online`` (Google only) or
    ``hybrid`` (Argos first, Google when a model is missing or fails).
    """

    use_online_fallback: bool = False
    model_manager: ArgosModelManager | None = None
    engine: str | None = None

    def create(self) -> BaseTranslator:
        engine = self.engine or ("hybrid" if self.use_online_fallback else "offline")
        if engine == "online":
            inner: BaseTranslator = GoogleFreeFallbackTranslator()
        elif engine == "hybrid":
            inner = HybridTranslator(
                primary=ArgosOfflineTranslator(self.model_manager),
                secondary=GoogleFreeFallbackTranslator(),
            )
        else:
            inner = ArgosOfflineTranslator(self.model_manager)
        return CachedTranslator(inner)
