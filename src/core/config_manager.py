import json
import threading
from pathlib import Path
from typing import Any, Dict


class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    DEFAULTS: Dict[str, Any] = {
        "source_lang": "auto",
        "target_lang": "en",
        "overlay_opacity": 0.85,
        "font_size": 14,
        "use_online_fallback": False,
        "region": {"x": 100, "y": 100, "width": 640, "height": 360},
        "hotkeys": {
            "toggle_translation": "Ctrl+Shift+R",
            "open_settings": "Ctrl+Shift+D",
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
        self.config_path = Path(config_path or "settings.json")
        self._data = dict(self.DEFAULTS)
        self.load()
        self._initialized = True

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with self.config_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            merged = dict(self.DEFAULTS)
            merged.update(loaded)
            if isinstance(loaded.get("hotkeys"), dict):
                merged["hotkeys"] = {**self.DEFAULTS["hotkeys"], **loaded["hotkeys"]}
            self._data = merged
        else:
            self.save()
        return self._data

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()
