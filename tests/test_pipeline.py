import unittest

import numpy as np

from src.core.image_processor import frame_signature, has_changed, sample_colors
from src.core.languages import detect_language, tesseract_languages
from src.core.pipeline import LiveLoop, TranslationPipeline
from src.translation.ocr_engine import TextBlock
from src.translation.translator import BaseTranslator


class Upper(BaseTranslator):
    def translate(self, text, source_lang, target_lang):
        return "id:" + text


class FakeOCR:
    def __init__(self):
        self.calls = 0

    def extract_blocks(self, frame):
        self.calls += 1
        return [TextBlock(text="hello there", box=(10, 10, 60, 20))]


def blank(value=255):
    return np.full((100, 200, 3), value, dtype=np.uint8)


class ImageTests(unittest.TestCase):
    def test_masked_changes_are_ignored(self):
        before = blank()
        after = blank()
        after[10:30, 10:70] = 0  # our overlay painted here
        mask = [(10, 10, 60, 20)]
        self.assertFalse(has_changed(frame_signature(before, mask), frame_signature(after, mask)))
        self.assertTrue(has_changed(frame_signature(before), frame_signature(after)))

    def test_sample_colors_dark_box(self):
        frame = blank(30)
        frame[20:30, 20:60] = 240  # light text strokes on a dark background
        background, text = sample_colors(frame, (15, 15, 50, 20))
        self.assertLess(sum(background), 150)
        self.assertGreater(sum(text), 600)


class LanguageTests(unittest.TestCase):
    def test_script_detection(self):
        self.assertEqual("ja", detect_language("これは日本語です"))
        self.assertEqual("ko", detect_language("안녕하세요"))
        self.assertEqual("zh", detect_language("这是中文"))

    def test_tesseract_language_mapping(self):
        self.assertEqual("jpn+eng", tesseract_languages("ja"))
        self.assertEqual("eng", tesseract_languages("auto"))
        self.assertEqual("eng", tesseract_languages("ja", installed=["eng", "osd"]))


class LiveLoopTests(unittest.TestCase):
    def make_loop(self, frames, live=True, peek_interval=0):
        ocr = FakeOCR()
        pipeline = TranslationPipeline(ocr, Upper(), "en", "id")
        shown, cleared = [], []
        frames = iter(frames)
        loop = LiveLoop(
            grab=lambda: next(frames),
            pipeline=pipeline,
            show=shown.append,
            clear=lambda: cleared.append(True),
            live=live,
            peek_interval=peek_interval,
            sleep=lambda s: None,
            clock=iter(range(1000)).__next__,
        )
        return loop, ocr, shown, cleared

    def test_overlay_does_not_retrigger_and_change_does(self):
        overlay_frame = blank()
        overlay_frame[10:30, 10:70] = 0  # what the screen looks like with our overlay
        changed = overlay_frame.copy()
        changed[60:90, 100:190] = 0  # new content elsewhere
        frames = [blank(), blank(), overlay_frame, overlay_frame, changed]
        loop, ocr, shown, cleared = self.make_loop(frames)
        for _ in range(5):
            loop.step()
        self.assertEqual(1, ocr.calls)
        self.assertEqual("id:hello there", shown[0][0].translated)
        self.assertEqual(1, len(cleared))
        self.assertEqual([], loop.shown_boxes)

    def test_peek_detects_text_changing_under_overlay(self):
        overlay_frame = blank()
        overlay_frame[10:30, 10:70] = 0
        new_text_under_box = blank()
        new_text_under_box[12:28, 12:68] = 100  # different text, same place
        frames = [blank(), blank(), overlay_frame, blank(), overlay_frame, new_text_under_box]
        loop, ocr, shown, cleared = self.make_loop(frames, peek_interval=1)
        for _ in range(3):
            loop.step()
        # first peek: nothing changed, the same translation is shown again
        self.assertEqual(1, ocr.calls)
        self.assertEqual(2, len(shown))
        loop.step()  # second peek sees the new text
        self.assertEqual([], loop.shown_boxes)

    def test_translate_once_stops_after_change(self):
        changed = blank()
        changed[60:90, 100:190] = 0
        loop, ocr, shown, cleared = self.make_loop([blank(), blank(), changed], live=False)
        loop.run()
        self.assertEqual(1, ocr.calls)
        self.assertEqual(1, len(shown))
        self.assertEqual(1, len(cleared))
        self.assertFalse(loop.running)


if __name__ == "__main__":
    unittest.main()
