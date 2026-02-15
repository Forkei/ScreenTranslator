import logging
import ctypes

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import QWidget, QApplication

from src.models.text_block import TextBlock

logger = logging.getLogger(__name__)

# Win32 constants
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

try:
    user32 = ctypes.windll.user32
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False


def _virtual_geometry() -> QRect:
    """Get the bounding rect of all monitors (virtual desktop)."""
    screen = QApplication.primaryScreen()
    if screen:
        return screen.virtualGeometry()
    return QRect(0, 0, 1920, 1080)


class OverlayWindow(QWidget):
    """Transparent click-through overlay that renders translated text blocks.

    Spans the entire virtual desktop (all monitors).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list[TextBlock] = []
        self._font_family = "Arial"
        self._overlay_opacity = 0.9
        self._show_background = True
        self._visible = False
        self._vg_offset_x = 0  # Virtual geometry x offset (can be negative)
        self._vg_offset_y = 0

        self._setup_window()

    def _setup_window(self):
        """Configure the overlay as a transparent, click-through, always-on-top window."""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Span all monitors
        self._update_geometry()

        self.show()
        self._apply_click_through()
        self.hide()

    def _update_geometry(self):
        """Set geometry to cover the full virtual desktop."""
        vg = _virtual_geometry()
        self.setGeometry(vg)
        self._vg_offset_x = vg.x()
        self._vg_offset_y = vg.y()

    def _apply_click_through(self):
        """Set Win32 extended styles for full click-through and exclude from capture."""
        if not HAS_WIN32:
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            # Exclude overlay from screen capture to prevent feedback loop
            if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                logger.warning("SetWindowDisplayAffinity failed — overlay may appear in captures")
            else:
                logger.debug("Overlay excluded from screen capture")

            logger.debug("Click-through applied to overlay")
        except Exception as e:
            logger.error("Failed to set click-through: %s", e)

    def set_font_family(self, family: str):
        self._font_family = family

    def set_overlay_opacity(self, opacity: float):
        self._overlay_opacity = max(0.0, min(1.0, opacity))

    def set_show_background(self, show: bool):
        self._show_background = show

    def update_blocks(self, blocks: list[TextBlock]):
        """Update the text blocks to render and trigger repaint."""
        self._blocks = blocks
        if blocks and not self._visible:
            self._update_geometry()
            self.show()
            self._apply_click_through()
            self._visible = True
        elif not blocks and self._visible:
            self.hide()
            self._visible = False
        self.update()

    def clear(self):
        """Clear all blocks and hide overlay."""
        self._blocks = []
        self.hide()
        self._visible = False

    def paintEvent(self, event):
        """Render translated text blocks with background rectangles.

        Two-pass rendering: all backgrounds first, then all text.
        This prevents text from one block overlapping another's background.
        """
        if not self._blocks:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # Global screen coords -> widget-local coords offset
        ox = self._vg_offset_x
        oy = self._vg_offset_y

        # Pre-compute layout for each block
        layouts = []
        for block in self._blocks:
            if not block.display_text:
                continue

            local_x = block.x - ox
            local_y = block.y - oy

            # Truncate translated text if >3x source length
            display = block.display_text
            if block.text and len(display) > len(block.text) * 3:
                max_chars = len(block.text) * 3
                display = display[:max_chars].rstrip() + "..."

            # Start with OCR-detected font size, then shrink to fit
            font_size = max(8, min(block.font_size, 48))
            font = QFont(self._font_family, font_size)
            metrics = QFontMetrics(font)

            measure_rect = QRect(0, 0, block.width, 10000)
            br = metrics.boundingRect(measure_rect, Qt.TextWordWrap, display)

            # Shrink font until text fits in the block height
            while font_size > 8 and br.height() > block.height + 4:
                font_size -= 1
                font = QFont(self._font_family, font_size)
                metrics = QFontMetrics(font)
                br = metrics.boundingRect(measure_rect, Qt.TextWordWrap, display)

            # Scale padding with font size
            pad = max(4, font_size // 5)

            text_rect = QRect(local_x, local_y, block.width, max(block.height, br.height()))
            bg_rect = QRect(
                local_x - pad, local_y - pad,
                block.width + pad * 2, max(block.height, br.height()) + pad * 2,
            )

            layouts.append((block, display, font, font_size, text_rect, bg_rect, pad))

        # --- Pass 1: Draw all backgrounds ---
        if self._show_background:
            painter.setPen(Qt.NoPen)
            for block, display, font, font_size, text_rect, bg_rect, pad in layouts:
                bg = QColor(*block.bg_color)
                bg.setAlphaF(self._overlay_opacity)
                painter.setBrush(bg)
                painter.drawRoundedRect(bg_rect, 3, 3)

        # --- Pass 2: Draw all text with clipping ---
        for block, display, font, font_size, text_rect, bg_rect, pad in layouts:
            painter.setFont(font)
            fg = QColor(*block.fg_color)
            painter.setPen(fg)
            painter.save()
            painter.setClipRect(bg_rect)
            painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignTop, display)
            painter.restore()

        painter.end()
