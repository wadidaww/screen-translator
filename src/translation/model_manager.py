import logging
import threading
from typing import Callable, Optional

try:
    import argostranslate.package as argos_package
except ImportError:  # pragma: no cover - optional dependency
    argos_package = None

LOGGER = logging.getLogger(__name__)


class ArgosModelManager:
    """Downloads Argos models on demand, pivoting through English when needed."""

    def __init__(self, progress_callback: Optional[Callable[[int], None]] = None):
        self.progress_callback = progress_callback
        self._index_loaded = False
        self._failed: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def _progress(self, value: int) -> None:
        if self.progress_callback:
            self.progress_callback(value)

    def _available(self):
        if not self._index_loaded:
            argos_package.update_package_index()
            self._index_loaded = True
        return argos_package.get_available_packages()

    def _install_pair(self, available, from_lang: str, to_lang: str) -> bool:
        installed = argos_package.get_installed_packages()
        if any(p.from_code == from_lang and p.to_code == to_lang for p in installed):
            return True
        match = next(
            (p for p in available if p.from_code == from_lang and p.to_code == to_lang), None
        )
        if not match:
            return False
        LOGGER.info("Downloading Argos model %s -> %s", from_lang, to_lang)
        argos_package.install_from_path(match.download())
        return True

    def ensure_model_installed(self, from_lang: str, to_lang: str) -> bool:
        if argos_package is None:
            LOGGER.warning("Argos Translate package is unavailable")
            return False
        key = (from_lang, to_lang)
        with self._lock:
            if key in self._failed:
                return False
            try:
                self._progress(10)
                available = self._available()
                ok = self._install_pair(available, from_lang, to_lang)
                if not ok and "en" not in key:
                    # Argos chains models automatically: src -> en -> target.
                    ok = self._install_pair(available, from_lang, "en") and self._install_pair(
                        available, "en", to_lang
                    )
                self._progress(100)
            except Exception:
                LOGGER.exception("Failed installing Argos model %s -> %s", from_lang, to_lang)
                ok = False
            if not ok:
                LOGGER.warning("No Argos package found for %s -> %s", from_lang, to_lang)
                self._failed.add(key)
            return ok
