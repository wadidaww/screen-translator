import unittest
from pathlib import Path
from unittest.mock import patch

from src.translation.ocr_engine import OCREngine


class OCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(__file__).parent / "fixtures" / "hello_world.png"
        cls.fixture.parent.mkdir(parents=True, exist_ok=True)
        # simple placeholder PNG bytes; OCR call is mocked in this test
        cls.fixture.write_bytes(
            bytes.fromhex(
                "89504E470D0A1A0A0000000D4948445200000001000000010802000000907724"
                "0000000A49444154789C6360000002000154A24F7D0000000049454E44AE426082"
            )
        )

    def test_extracts_hello_world(self):
        engine = OCREngine(confidence_threshold=70)
        frame = self.fixture.read_bytes()

        mocked_result = {
            "text": ["Hello,", "World!"],
            "conf": ["95", "96"],
        }

        with patch("src.translation.ocr_engine.preprocess_for_ocr", return_value=frame), patch(
            "src.translation.ocr_engine.pytesseract"
        ) as mock_tesseract:
            mock_tesseract.Output.DICT = object()
            mock_tesseract.image_to_data.return_value = mocked_result
            result = engine.extract_text(frame)

        self.assertIn("Hello, World!", result["text"])
        self.assertGreaterEqual(result["confidence"], 90)


if __name__ == "__main__":
    unittest.main()
