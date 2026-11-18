import unittest
from unittest.mock import patch

import numpy as np

from src.translation.ocr_engine import OCREngine, join_words


def tesseract_data(words):
    """Build an image_to_data dict from (text, block, par, line, left, top, w, h, conf)."""
    keys = ["text", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf"]
    data = {k: [] for k in keys}
    for word in words:
        for key, value in zip(keys, word):
            data[key].append(value)
    return data


class OCRTests(unittest.TestCase):
    def test_extracts_hello_world(self):
        engine = OCREngine(confidence_threshold=70)
        frame = np.zeros((40, 200, 3), dtype=np.uint8)
        mocked = tesseract_data(
            [
                ("Hello,", 1, 1, 1, 10, 10, 50, 20, "95"),
                ("World!", 1, 1, 1, 70, 10, 60, 20, "96"),
            ]
        )
        with (
            patch("src.translation.ocr_engine.preprocess_for_ocr", return_value=(frame, 1.0)),
            patch("src.translation.ocr_engine.pytesseract") as mock_tesseract,
        ):
            mock_tesseract.image_to_data.return_value = mocked
            mock_tesseract.get_languages.return_value = ["eng"]
            result = engine.extract_text(frame)

        self.assertIn("Hello, World!", result["text"])
        self.assertGreaterEqual(result["confidence"], 90)

    def test_groups_words_into_paragraph_boxes_and_rescales(self):
        engine = OCREngine()
        data = tesseract_data(
            [
                ("Good", 1, 1, 1, 20, 20, 80, 30, "90"),
                ("morning", 1, 1, 1, 110, 20, 140, 30, "92"),
                ("everyone", 1, 1, 2, 20, 60, 160, 30, "91"),
                ("~", 1, 1, 2, 300, 60, 10, 30, "10"),  # low confidence, dropped
                ("Settings", 2, 1, 1, 400, 200, 160, 30, "88"),
            ]
        )
        blocks = engine.group_tesseract_data(data, scale=2.0)
        self.assertEqual(2, len(blocks))
        self.assertEqual("Good morning everyone", blocks[0].text)
        self.assertEqual((10, 10, 115, 35), blocks[0].box)
        self.assertEqual(["Good morning", "everyone"], blocks[0].lines)
        self.assertEqual("Settings", blocks[1].text)

    def test_cjk_words_are_joined_without_spaces(self):
        self.assertEqual("こんにちは世界", join_words(["こんにちは", "世界"]))
        self.assertEqual("Hello world", join_words(["Hello", "world"]))

    def test_noise_detection(self):
        self.assertTrue(OCREngine.is_noise("|"))
        self.assertTrue(OCREngine.is_noise("— · ·"))
        self.assertFalse(OCREngine.is_noise("OK"))
        self.assertFalse(OCREngine.is_noise("字"))


if __name__ == "__main__":
    unittest.main()
