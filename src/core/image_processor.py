"""Image helpers: OCR pre-processing, colour sampling and change detection."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None

Box = Tuple[int, int, int, int]  # x, y, width, height
Color = Tuple[int, int, int]

SIGNATURE_WIDTH = 160
PIXEL_DIFF_THRESHOLD = 24
CHANGED_RATIO_THRESHOLD = 0.004


def to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    if cv2 is not None:
        return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return (frame[:, :, :3].astype(np.float32) @ weights).astype(np.uint8)


def ocr_scale_for(height: int) -> float:
    """Upscale small captures so tesseract sees ~30px tall glyphs."""
    if height <= 500:
        return 2.0
    if height <= 1100:
        return 1.5
    return 1.0


def preprocess_for_ocr(frame: Any) -> Tuple[Any, float]:
    """Return ``(image, scale)`` where image is grey, dark-text-on-light and upscaled.

    Bounding boxes found on the returned image must be divided by ``scale``
    to map back to the original frame.
    """
    if not isinstance(frame, np.ndarray):
        return frame, 1.0
    gray = to_gray(frame)
    if float(gray.mean()) < 110:  # dark mode: invert so text is dark on light
        gray = 255 - gray
    scale = ocr_scale_for(gray.shape[0])
    if scale != 1.0 and cv2 is not None:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    elif scale != 1.0:
        scale = 1.0
    return gray, scale


def _clip_box(box: Box, width: int, height: int) -> Optional[Box]:
    x, y, w, h = box
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1 - x0, y1 - y0


def sample_colors(frame: np.ndarray, box: Box, ring: int = 3) -> Tuple[Color, Color]:
    """Estimate (background, text) colours for a text box in an RGB frame."""
    height, width = frame.shape[:2]
    outer = _clip_box(
        (box[0] - ring, box[1] - ring, box[2] + 2 * ring, box[3] + 2 * ring), width, height
    )
    inner = _clip_box(box, width, height)
    if outer is None or inner is None:
        return (255, 255, 255), (0, 0, 0)

    ox, oy, ow, oh = outer
    patch = frame[oy : oy + oh, ox : ox + ow, :3].reshape(-1, 3).astype(np.int32)
    ix, iy, iw, ih = inner
    mask = np.ones((oh, ow), dtype=bool)
    mask[iy - oy : iy - oy + ih, ix - ox : ix - ox + iw] = False
    border = patch[mask.reshape(-1)]
    if border.size == 0:
        border = patch
    background = np.median(border, axis=0)

    inside = frame[iy : iy + ih, ix : ix + iw, :3].reshape(-1, 3).astype(np.int32)
    distance = np.abs(inside - background).sum(axis=1)
    cutoff = np.percentile(distance, 90) if distance.size else 0
    strong = inside[distance >= cutoff] if distance.size else inside
    text = strong.mean(axis=0) if strong.size else np.array([0, 0, 0])

    bg = tuple(int(c) for c in background)
    fg = tuple(int(c) for c in text)
    if contrast(bg, fg) < 90:
        fg = (0, 0, 0) if luminance(bg) > 140 else (255, 255, 255)
    return bg, fg


def luminance(color: Color) -> float:
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def contrast(a: Color, b: Color) -> float:
    return abs(luminance(a) - luminance(b))


def frame_signature(frame: np.ndarray, masked: Iterable[Box] = ()) -> Tuple[np.ndarray, np.ndarray]:
    """Return a small grey thumbnail plus a validity mask for change detection.

    ``masked`` boxes (in frame pixels) are excluded, so pixels covered by our
    own overlay never count as a change.
    """
    gray = to_gray(frame)
    step = max(1, gray.shape[1] // SIGNATURE_WIDTH)
    thumb = gray[::step, ::step].astype(np.int16)
    valid = np.ones(thumb.shape, dtype=bool)
    for x, y, w, h in masked:
        x0, y0 = max(0, (x - 4) // step), max(0, (y - 4) // step)
        x1, y1 = (x + w + 4) // step + 1, (y + h + 4) // step + 1
        valid[y0:y1, x0:x1] = False
    return thumb, valid


def has_changed(
    previous: Optional[Tuple[np.ndarray, np.ndarray]],
    current: Tuple[np.ndarray, np.ndarray],
    ratio: float = CHANGED_RATIO_THRESHOLD,
) -> bool:
    if previous is None:
        return True
    prev_thumb, prev_valid = previous
    thumb, valid = current
    if prev_thumb.shape != thumb.shape:
        return True
    usable = prev_valid & valid
    count = int(usable.sum())
    if count == 0:
        return False
    diff = np.abs(prev_thumb - thumb) > PIXEL_DIFF_THRESHOLD
    return float((diff & usable).sum()) / count > ratio


def union_box(boxes: Sequence[Box]) -> Box:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return x0, y0, x1 - x0, y1 - y0
