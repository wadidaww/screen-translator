"""Transparent, click-through window that paints translations over the original text."""

from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass
from typing import List, Sequence

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

LOGGER = logging.getLogger(__name__)
WDA_EXCLUDEFROMCAPTURE = 0x11
BOX_PADDING = 3
MIN_FONT_PX = 7
MAX_FONT_PX = 64


@dataclass
class OverlayItem:
    """A translated block in overlay (logical pixel) coordinates."""

    rect: QRect
    text: str
    background: QColor
    foreground: QColor


def fit_font_size(text: str, rect: QRect, base_font: QFont, fixed_px: int = 0) -> int:
    """Largest pixel size (binary search) at which ``text`` word-wraps inside ``rect``."""
    if fixed_px:
        return fixed_px
    flags = int(Qt.TextFlag.TextWordWrap)
    low, high = MIN_FONT_PX, max(MIN_FONT_PX, min(MAX_FONT_PX, rect.height()))
    best = low
    font = QFont(base_font)
    while low <= high:
        mid = (low + high) // 2
        font.setPixelSize(mid)
        bounds = QFontMetrics(font).boundingRect(rect, flags, text)
        if bounds.width() <= rect.width() and bounds.height() <= rect.height():
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def exclude_from_capture(widget: QWidget) -> bool:
    """Ask the OS to hide ``widget`` from screenshots so OCR never reads our overlay."""
    try:
        if sys.platform.startswith("win"):
            hwnd = int(widget.winId())
            return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
        if sys.platform == "darwin":
            import objc  # type: ignore  # pyobjc, optional

            view = objc.objc_object(c_void_p=int(widget.winId()))
            view.window().setSharingType_(0)  # NSWindowSharingNone
            return True
    except Exception:
        LOGGER.info("Overlay cannot be excluded from capture; using hide-and-capture")
    return False


class OverlayWindow(QWidget):
    def __init__(self, opacity: float = 1.0, font_size: int = 0):
        super().__init__()
        flags = (
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if sys.platform.startswith("linux"):
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.opacity = opacity
        self.font_size = font_size
        self.items: List[OverlayItem] = []
        self.excluded_from_capture = False
        self._exclusion_tried = False

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if not self._exclusion_tried:
            self._exclusion_tried = True
            self.excluded_from_capture = exclude_from_capture(self)

    def set_items(self, items: Sequence[OverlayItem]) -> None:
        self.items = list(items)
        self.update()

    @pyqtSlot()
    def clear_now(self) -> None:
        """Remove all translations and repaint synchronously (used before a clean capture)."""
        self.items = []
        self.repaint()

    def set_text(self, text: str) -> None:
        """Simple mode: show one block of text in the top-left corner."""
        rect = QRect(8, 8, max(200, self.width() - 16), max(60, self.height() // 4))
        self.set_items([OverlayItem(rect, text, QColor(20, 20, 20), QColor(255, 255, 255))])

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.items:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        base_font = QFont(self.font())
        for item in self.items:
            rect = item.rect.adjusted(-BOX_PADDING, -BOX_PADDING, BOX_PADDING, BOX_PADDING)
            background = QColor(item.background)
            background.setAlphaF(max(0.0, min(1.0, self.opacity)))
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 3, 3)
            painter.fillPath(path, background)

            text_rect = item.rect
            font = QFont(base_font)
            font.setPixelSize(fit_font_size(item.text, text_rect, base_font, self.font_size))
            painter.setFont(font)
            painter.setPen(item.foreground)
            painter.setClipRect(rect)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                | int(Qt.TextFlag.TextWordWrap),
                item.text,
            )
            painter.setClipping(False)
        painter.end()
