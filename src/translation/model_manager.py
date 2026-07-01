import logging
from typing import Callable, Optional

try:
    import argostranslate.package as argos_package
except ImportError:  # pragma: no cover
    argos_package = None

LOGGER = logging.getLogger(__name__)


class ArgosModelManager:
    def __init__(self, progress_callback: Optional[Callable[[int], None]] = None):
        self.progress_callback = progress_callback

    def ensure_model_installed(self, from_lang: str, to_lang: str) -> bool:
        if argos_package is None:
            LOGGER.warning("Argos Translate package is unavailable")
            return False

        argos_package.update_package_index()
        available = argos_package.get_available_packages()
        match = next(
            (
                pkg
                for pkg in available
                if pkg.from_code == from_lang and pkg.to_code == to_lang
            ),
            None,
        )
        if not match:
            LOGGER.warning("No Argos package found for %s -> %s", from_lang, to_lang)
            return False

        if self.progress_callback:
            self.progress_callback(10)
        path = match.download()
        if self.progress_callback:
            self.progress_callback(70)
        argos_package.install_from_path(path)
        if self.progress_callback:
            self.progress_callback(100)
        return True
