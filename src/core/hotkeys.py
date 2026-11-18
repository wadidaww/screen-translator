"""System-wide hotkeys via pynput (optional). Callbacks fire on a background thread."""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

try:
    from pynput import keyboard
except Exception:  # pragma: no cover - optional dependency / no display
    keyboard = None

LOGGER = logging.getLogger(__name__)

_MODIFIERS = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "shift": "<shift>",
    "alt": "<alt>",
    "option": "<alt>",
    "meta": "<cmd>",
    "win": "<cmd>",
    "cmd": "<cmd>",
    "super": "<cmd>",
}


def to_pynput(combo: str) -> str:
    """Convert ``Ctrl+Shift+T`` style text to pynput's ``<ctrl>+<shift>+t``."""
    parts = []
    for raw in combo.split("+"):
        key = raw.strip().lower()
        if not key:
            continue
        if key in _MODIFIERS:
            parts.append(_MODIFIERS[key])
        elif len(key) == 1:
            parts.append(key)
        else:
            parts.append(f"<{key}>")
    return "+".join(parts)


class GlobalHotkeys:
    def __init__(self):
        self._listener = None

    @staticmethod
    def available() -> bool:
        return keyboard is not None

    def start(self, bindings: Dict[str, Callable[[], None]]) -> bool:
        self.stop()
        if keyboard is None or not bindings:
            return False
        mapping: Dict[str, Callable[[], None]] = {}
        for combo, callback in bindings.items():
            if combo:
                mapping[to_pynput(combo)] = callback
        try:
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.start()
            return True
        except Exception:
            LOGGER.exception("Global hotkeys unavailable")
            self._listener = None
            return False

    def stop(self) -> None:
        listener: Optional[object] = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # pragma: no cover
                pass
