import copy
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List

LOGGER = logging.getLogger(__name__)


def default_config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "OmniViewTranslator"


class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    DEFAULTS: Dict[str, Any] = {
        "source_lang": "auto",
        "target_lang": "en",
        # offline = Argos only, online = Google only, hybrid = Argos then Google
        "translator_engine": "hybrid",
        "use_online_fallback": True,
        "overlay_opacity": 1.0,
        "font_size": 0,  # 0 = fit text to the original box
        "refresh_interval_ms": 600,
        # Linux only: how often to peek under the overlay for text that changed in place
        "peek_interval_ms": 2500,
        "show_floating_button": True,
        "tesseract_cmd": "",
        "region": None,  # None = whole primary screen
        "hotkeys": {
            "toggle_translation": "Ctrl+Shift+T",
            "translate_once": "Ctrl+Shift+O",
            "select_region": "Ctrl+Shift+R",
        },
    }

    def __new__(cls, config_path: str | None = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str | None = None):
        if self._initialized:
            return
        env_path = os.environ.get("OMNIVIEW_CONFIG")
        self.config_path = Path(config_path or env_path or default_config_dir() / "settings.json")
        self._data = copy.deepcopy(self.DEFAULTS)
        self._listeners: List[Callable[[str, Any], None]] = []
        self.load()
        self._initialized = True

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def load(self) -> Dict[str, Any]:
        merged = copy.deepcopy(self.DEFAULTS)
        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as file:
                    loaded = json.load(file)
            except (OSError, ValueError):
                LOGGER.exception("Could not read %s, using defaults", self.config_path)
                loaded = {}
            if isinstance(loaded, dict):
                merged.update(loaded)
                if isinstance(loaded.get("hotkeys"), dict):
                    merged["hotkeys"] = {**self.DEFAULTS["hotkeys"], **loaded["hotkeys"]}
                else:
                    merged["hotkeys"] = copy.deepcopy(self.DEFAULTS["hotkeys"])
            self._data = merged
        else:
            self._data = merged
            self.save()
        return self._data

    def save(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config_path.open("w", encoding="utf-8") as file:
                json.dump(self._data, file, indent=2)
        except OSError:
            LOGGER.exception("Could not save settings to %s", self.config_path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()
        for listener in list(self._listeners):
            listener(key, value)

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        self._listeners.append(listener)
