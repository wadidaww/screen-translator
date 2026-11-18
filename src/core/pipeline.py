"""Qt-free capture -> OCR -> translate pipeline and the live change-detection loop."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from src.core.image_processor import Box, frame_signature, has_changed, sample_colors
from src.core.languages import detect_language
from src.translation.ocr_engine import OCREngine, TextBlock
from src.translation.translator import BaseTranslator

LOGGER = logging.getLogger(__name__)
STABLE_WAIT_SECONDS = 0.25
MAX_UNSTABLE_SECONDS = 2.0
MASK_MARGIN = 8


def _same_text(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


class TranslationPipeline:
    def __init__(self, ocr: OCREngine, translator: BaseTranslator, source: str, target: str):
        self.ocr = ocr
        self.translator = translator
        self.source = source
        self.target = target
        self.online_auto = False  # True when the translator detects the language itself

    def translate_blocks(self, blocks: List[TextBlock]) -> List[TextBlock]:
        groups: dict[str, List[TextBlock]] = defaultdict(list)
        for block in blocks:
            if self.source != "auto":
                lang = self.source
            else:
                lang = detect_language(block.text, fallback="en")
            if lang == self.target:
                continue  # already in the target language: leave the original visible
            groups["auto" if self.online_auto and self.source == "auto" else lang].append(block)

        for lang, group in groups.items():
            try:
                results = self.translator.translate_batch(
                    [b.text for b in group], lang, self.target
                )
            except Exception:
                LOGGER.exception("Translation failed for %s -> %s", lang, self.target)
                continue
            for block, translated in zip(group, results):
                block.translated = translated or ""
        return [b for b in blocks if b.translated and not _same_text(b.translated, b.text)]

    def run(self, frame: np.ndarray) -> List[TextBlock]:
        blocks = self.ocr.extract_blocks(frame)
        if not blocks:
            return []
        translated = self.translate_blocks(blocks)
        for block in translated:
            block.background, block.foreground = sample_colors(frame, block.box)
        return translated


def expand(boxes: Sequence[Box], margin: int = MASK_MARGIN) -> List[Box]:
    return [(x - margin, y - margin, w + 2 * margin, h + 2 * margin) for x, y, w, h in boxes]


@dataclass
class LiveLoop:
    """Change-driven loop shared by live and one-shot modes.

    * ``grab()`` returns the current frame.
    * ``show(blocks)`` paints translations, ``clear()`` removes them and returns
      once the screen no longer shows them.
    * When the overlay cannot be excluded from screenshots, pixels under our own
      boxes are masked out so the overlay never triggers a re-translation. Text
      that changes *under* a box (game dialogue, subtitles) is caught by a
      periodic "peek": hide the overlay for one frame and compare with the frame
      that was translated.
    """

    grab: Callable[[], np.ndarray]
    pipeline: TranslationPipeline
    show: Callable[[List[TextBlock]], None]
    clear: Callable[[], None]
    overlay_excluded: Callable[[], bool] = lambda: False
    live: bool = True
    interval: float = 0.6
    peek_interval: float = 2.5
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    on_busy: Callable[[bool], None] = lambda busy: None
    running: bool = True
    shown_boxes: List[Box] = field(default_factory=list)
    _baseline: Optional[Tuple[np.ndarray, np.ndarray]] = None
    _previous: Optional[Tuple[np.ndarray, np.ndarray]] = None
    _unstable_since: Optional[float] = None
    _translated_once: bool = False
    _clean: Optional[Tuple[np.ndarray, np.ndarray]] = None
    _blocks: List[TextBlock] = field(default_factory=list)
    _last_peek: float = 0.0

    def stop(self) -> None:
        self.running = False

    def _mask(self) -> List[Box]:
        if self.shown_boxes and not self.overlay_excluded():
            return expand(self.shown_boxes)
        return []

    def _should_peek(self) -> bool:
        return (
            self.live
            and self.peek_interval > 0
            and not self.overlay_excluded()
            and self.clock() - self._last_peek >= self.peek_interval
        )

    def step(self) -> None:
        frame = self.grab()
        if self.shown_boxes:
            changed = has_changed(self._baseline, frame_signature(frame, self._mask()))
            if not changed and self._should_peek():
                self.clear()
                self._last_peek = self.clock()
                changed = has_changed(self._clean, frame_signature(self.grab()))
                if not changed:
                    self.show(self._blocks)  # nothing new under our boxes
                    self.sleep(self.interval)
                    return
            elif not changed:
                self.sleep(self.interval)
                return
            # Screen changed under/around the overlay: translations are stale.
            self.clear()
            self.shown_boxes = []
            self._baseline = None
            self._previous = None
            if not self.live:
                self.running = False
                return
            self._unstable_since = self.clock()
            self.sleep(0.1)
            return

        if self._translated_once and not self.live:
            self.running = False
            return

        signature = frame_signature(frame)
        if self._baseline is not None and not has_changed(self._baseline, signature):
            self.sleep(self.interval)
            return

        # Wait until the screen stops moving (scrolling, animations) before OCR.
        now = self.clock()
        if self._unstable_since is None:
            self._unstable_since = now
        waited = now - self._unstable_since
        if self.live and (self._previous is None or has_changed(self._previous, signature)):
            if waited < MAX_UNSTABLE_SECONDS:
                self._previous = signature
                self.sleep(STABLE_WAIT_SECONDS)
                return

        self.on_busy(True)
        try:
            blocks = self.pipeline.run(frame)
        finally:
            self.on_busy(False)
        self._translated_once = True
        self._previous = None
        self._unstable_since = None
        if not self.running:
            return
        if blocks:
            self.show(blocks)
            self._blocks = blocks
            self.shown_boxes = [b.box for b in blocks]
            self._baseline = frame_signature(frame, self._mask())
            self._clean = signature
            self._last_peek = self.clock()
        else:
            self._baseline = signature
            if not self.live:
                self.running = False

    def run(self) -> None:
        while self.running:
            try:
                self.step()
            except Exception:
                LOGGER.exception("Translation loop step failed")
                self.sleep(1.0)
