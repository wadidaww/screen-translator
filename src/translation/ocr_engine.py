"""OCR that returns positioned text blocks (paragraphs) instead of one big string."""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.image_processor import Box, preprocess_for_ocr, union_box
from src.core.languages import NO_SPACE_LANGS, tesseract_languages

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency
    pytesseract = None

try:
    import easyocr
except ImportError:  # pragma: no cover - optional dependency
    easyocr = None

LOGGER = logging.getLogger(__name__)
MIN_ALPHA_RATIO = 0.2
ALPHA_PATTERN = r"[A-Za-z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u0E00-\u0E7F\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]"
CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def bundled_tesseract() -> Optional[str]:
    """Tesseract shipped next to the packaged app (the Windows build puts it in ./tesseract)."""
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(meipass)
    exe = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
    for root in roots:
        candidate = os.path.join(root, "tesseract", exe)
        if os.path.isfile(candidate):
            return candidate
    return None


@dataclass
class TextBlock:
    """A paragraph of recognised text and its box in frame pixel coordinates."""

    text: str
    box: Box
    confidence: int = 0
    lines: List[str] = field(default_factory=list)
    translated: str = ""
    background: tuple = (255, 255, 255)
    foreground: tuple = (0, 0, 0)


def join_words(words: List[str]) -> str:
    """Join OCR words, without spaces between CJK characters."""
    out = ""
    for word in words:
        if out and not (CJK_PATTERN.search(out[-1]) and CJK_PATTERN.search(word[0])):
            out += " "
        out += word
    return out


class OCREngine:
    def __init__(
        self,
        confidence_threshold: int = 70,
        source_lang: str = "auto",
        tesseract_cmd: Optional[str] = None,
        min_word_confidence: int = 35,
    ):
        self.confidence_threshold = confidence_threshold
        self.min_word_confidence = min_word_confidence
        self.source_lang = source_lang
        self._easy_reader = None
        self._installed_langs: Optional[List[str]] = None
        self._configure_tesseract(tesseract_cmd)

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _configure_tesseract(tesseract_cmd: Optional[str]) -> None:
        if pytesseract is None:
            return
        cmd = tesseract_cmd or os.environ.get("TESSERACT_CMD") or bundled_tesseract()
        if not cmd and not shutil.which("tesseract") and os.path.exists(WINDOWS_TESSERACT):
            cmd = WINDOWS_TESSERACT
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

    @staticmethod
    def tesseract_available() -> bool:
        if pytesseract is None:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def installed_languages(self) -> Optional[List[str]]:
        if self._installed_langs is None and pytesseract is not None:
            try:
                self._installed_langs = list(pytesseract.get_languages(config=""))
            except Exception:
                self._installed_langs = None
        return self._installed_langs

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def is_noise(text: str) -> bool:
        if not text:
            return True
        cleaned = text.strip()
        if len(cleaned) < 2 and not CJK_PATTERN.search(cleaned):
            return True
        alpha_ratio = len(re.findall(ALPHA_PATTERN, cleaned)) / max(1, len(cleaned))
        return alpha_ratio < MIN_ALPHA_RATIO

    def group_tesseract_data(self, data: Dict[str, list], scale: float = 1.0) -> List[TextBlock]:
        """Group tesseract ``image_to_data`` words into paragraph blocks."""
        paragraphs: Dict[tuple, Dict[tuple, list]] = {}
        texts = data.get("text", [])
        for i, raw in enumerate(texts):
            word = str(raw).strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (KeyError, ValueError, IndexError):
                conf = -1
            if conf < self.min_word_confidence:
                continue
            para_key = (data["block_num"][i], data["par_num"][i])
            line_key = data["line_num"][i]
            box = (
                int(data["left"][i] / scale),
                int(data["top"][i] / scale),
                max(1, int(data["width"][i] / scale)),
                max(1, int(data["height"][i] / scale)),
            )
            paragraphs.setdefault(para_key, {}).setdefault(line_key, []).append((word, box, conf))

        blocks: List[TextBlock] = []
        for lines in paragraphs.values():
            line_texts, boxes, confs = [], [], []
            for line_key in sorted(lines):
                words = lines[line_key]
                line_texts.append(join_words([w for w, _, _ in words]))
                boxes.extend(b for _, b, _ in words)
                confs.extend(c for _, _, c in words)
            text = (
                join_words(line_texts)
                if self.source_lang in NO_SPACE_LANGS
                else " ".join(line_texts)
            )
            if self.is_noise(text):
                continue
            blocks.append(
                TextBlock(
                    text=text,
                    box=union_box(boxes),
                    confidence=int(sum(confs) / len(confs)),
                    lines=line_texts,
                )
            )
        blocks.sort(key=lambda b: (b.box[1], b.box[0]))
        return blocks

    # ------------------------------------------------------------------- OCR
    def _blocks_with_tesseract(self, image: Any, scale: float) -> List[TextBlock]:
        if pytesseract is None:
            return []
        lang = tesseract_languages(self.source_lang, self.installed_languages())
        data = pytesseract.image_to_data(
            image, lang=lang, config="--psm 3", output_type=pytesseract.Output.DICT
        )
        return self.group_tesseract_data(data, scale)

    def _blocks_with_easyocr(self, image: Any, scale: float) -> List[TextBlock]:
        if easyocr is None:
            return []
        if self._easy_reader is None:
            langs = ["en"]
            if self.source_lang in {"ja", "ko", "zh"}:
                langs = [{"zh": "ch_sim"}.get(self.source_lang, self.source_lang), "en"]
            self._easy_reader = easyocr.Reader(langs, gpu=False)
        blocks = []
        for points, text, conf in self._easy_reader.readtext(image, paragraph=False):
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            box = (
                int(min(xs) / scale),
                int(min(ys) / scale),
                int((max(xs) - min(xs)) / scale),
                int((max(ys) - min(ys)) / scale),
            )
            if not self.is_noise(text):
                blocks.append(TextBlock(text=text, box=box, confidence=int(conf * 100)))
        return blocks

    def extract_blocks(self, frame: Any) -> List[TextBlock]:
        processed, scale = preprocess_for_ocr(frame)
        blocks: List[TextBlock] = []
        try:
            blocks = self._blocks_with_tesseract(processed, scale)
        except Exception:
            LOGGER.exception("Tesseract OCR failed")
        if not blocks and easyocr is not None:
            try:
                blocks = self._blocks_with_easyocr(processed, scale)
            except Exception:
                LOGGER.exception("EasyOCR failed")
        return blocks

    def extract_text(self, frame: Any) -> Dict[str, int | str]:
        """Backwards compatible API: all text joined plus average confidence."""
        blocks = self.extract_blocks(frame)
        if not blocks:
            return {"text": "", "confidence": 0}
        text = " ".join(b.text for b in blocks)
        confidence = int(sum(b.confidence for b in blocks) / len(blocks))
        return {"text": text, "confidence": confidence}
