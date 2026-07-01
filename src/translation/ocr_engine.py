import logging
import re
from typing import Any, Dict

from src.core.image_processor import preprocess_for_ocr

try:
    import easyocr
except Exception:  # pragma: no cover
    easyocr = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

LOGGER = logging.getLogger(__name__)


class OCREngine:
    def __init__(self, confidence_threshold: int = 70):
        self.confidence_threshold = confidence_threshold
        self._easy_reader = None

    def _extract_with_tesseract(self, image: Any) -> Dict[str, int | str]:
        if pytesseract is None:
            return {"text": "", "confidence": 0}
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        words = [w.strip() for w in data.get("text", []) if w.strip()]
        confidences = [int(float(c)) for c in data.get("conf", []) if str(c).strip() not in {"", "-1"}]
        text = " ".join(words)
        confidence = int(sum(confidences) / len(confidences)) if confidences else 0
        return {"text": text, "confidence": confidence}

    def _extract_with_easyocr(self, image: Any) -> Dict[str, int | str]:
        if easyocr is None:
            return {"text": "", "confidence": 0}
        if self._easy_reader is None:
            self._easy_reader = easyocr.Reader(["en"], gpu=False)
        results = self._easy_reader.readtext(image)
        if not results:
            return {"text": "", "confidence": 0}
        text = " ".join([item[1] for item in results])
        confidence = int(sum(item[2] for item in results) / len(results) * 100)
        return {"text": text, "confidence": confidence}

    @staticmethod
    def _is_noise(text: str) -> bool:
        if not text:
            return True
        cleaned = text.strip()
        if len(cleaned) < 2:
            return True
        alpha_ratio = len(re.findall(r"[A-Za-z\u00C0-\u024F]", cleaned)) / max(1, len(cleaned))
        return alpha_ratio < 0.2

    def extract_text(self, frame: Any) -> Dict[str, int | str]:
        processed = preprocess_for_ocr(frame)
        result = self._extract_with_tesseract(processed)
        if result["confidence"] < self.confidence_threshold or self._is_noise(str(result["text"])):
            LOGGER.warning("Low confidence OCR (%s), falling back to EasyOCR", result["confidence"])
            result = self._extract_with_easyocr(processed)
        del processed
        return {"text": str(result["text"]).strip(), "confidence": int(result["confidence"])}
