from typing import Any

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def preprocess_for_ocr(frame: Any) -> Any:
    if cv2 is None:
        return frame
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    upscaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    return cv2.adaptiveThreshold(
        upscaled,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
