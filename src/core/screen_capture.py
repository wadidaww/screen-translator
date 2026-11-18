import logging
import threading
import time
from typing import Any, Optional, Tuple

import numpy as np

try:
    import mss
except ImportError:  # pragma: no cover - optional dependency
    mss = None

LOGGER = logging.getLogger(__name__)
BBox = Tuple[int, int, int, int]


class ScreenGrabber:
    """Grabs a screen rectangle (physical pixels) as an RGB numpy array.

    An ``mss`` handle is bound to the thread that created it, so create one
    grabber per worker thread.
    """

    def __init__(self):
        if mss is None:
            raise RuntimeError("mss is not installed (pip install mss)")
        self._sct = mss.mss()

    def grab(self, bbox: BBox) -> np.ndarray:
        x, y, width, height = bbox
        raw = self._sct.grab({"left": x, "top": y, "width": width, "height": height})
        frame = np.asarray(raw)  # BGRA
        return frame[:, :, 2::-1].copy()  # -> RGB

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:  # pragma: no cover
            pass


class RegionCapture:
    """Background capture loop keeping the latest frame of a region."""

    def __init__(self, bbox: BBox, fps: int = 15):
        self.x, self.y, self.width, self.height = bbox
        self.fps = max(1, fps)
        self._latest_frame: Optional[Any] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _capture_loop(self) -> None:
        interval = 1.0 / self.fps
        grabber = ScreenGrabber()
        try:
            while not self._stop_event.is_set():
                started = time.time()
                try:
                    frame = grabber.grab((self.x, self.y, self.width, self.height))
                    with self._lock:
                        self._latest_frame = frame
                except Exception as exc:  # pragma: no cover
                    LOGGER.exception("Capture loop failed: %s", exc)
                elapsed = time.time() - started
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            grabber.close()

    def grab_frame(self) -> Optional[Any]:
        with self._lock:
            if self._latest_frame is None:
                return None
            if hasattr(self._latest_frame, "copy"):
                return self._latest_frame.copy()
            return self._latest_frame
