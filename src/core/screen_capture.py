import logging
import threading
import time
from typing import Any, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None

LOGGER = logging.getLogger(__name__)


class RegionCapture:
    def __init__(self, bbox: Tuple[int, int, int, int], fps: int = 15):
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
        while not self._stop_event.is_set():
            started = time.time()
            try:
                frame = self._capture_once()
                if frame is not None:
                    with self._lock:
                        self._latest_frame = frame
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Capture loop failed: %s", exc)
            elapsed = time.time() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _capture_once(self) -> Optional[Any]:
        if np is None:
            raise RuntimeError("numpy is not installed")
        if mss is None:
            raise RuntimeError("mss is not installed")
        monitor = {"top": self.y, "left": self.x, "width": self.width, "height": self.height}
        with mss.mss() as sct:
            raw = sct.grab(monitor)
        frame = np.array(raw)
        return frame[:, :, :3][:, :, ::-1].copy()

    def grab_frame(self) -> Optional[Any]:
        with self._lock:
            if self._latest_frame is None:
                return None
            if hasattr(self._latest_frame, "copy"):
                return self._latest_frame.copy()
            return self._latest_frame
