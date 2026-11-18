import unittest

from src.core.screen_capture import RegionCapture


class RegionCaptureTests(unittest.TestCase):
    class DummyFrame:
        def __init__(self, value):
            self.value = value

        def copy(self):
            return RegionCaptureTests.DummyFrame(self.value)

    def test_grab_frame_returns_copy(self):
        capture = RegionCapture((0, 0, 10, 10), fps=1)
        frame = self.DummyFrame("frame")
        capture._latest_frame = frame

        grabbed = capture.grab_frame()
        self.assertIsNotNone(grabbed)
        self.assertEqual(frame.value, grabbed.value)
        self.assertIsNot(frame, grabbed)


if __name__ == "__main__":
    unittest.main()
