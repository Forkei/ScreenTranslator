import logging

from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import QWidget, QApplication

logger = logging.getLogger(__name__)


def _virtual_geometry() -> QRect:
    """Get the bounding rect of all monitors (virtual desktop)."""
    screen = QApplication.primaryScreen()
    if screen:
        return screen.virtualGeometry()
    return QRect(0, 0, 1920, 1080)


class RegionSelector(QWidget):
    """Semi-transparent overlay spanning ALL monitors for click-drag region selection."""

    region_selected = pyqtSignal(tuple)  # (x, y, w, h)
    selection_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._origin = QPoint()
        self._current = QPoint()
        self._selecting = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)

    def start_selection(self):
        """Show the selector spanning all monitors."""
        self._selecting = False
        # Set geometry to full virtual desktop (all monitors)
        vg = _virtual_geometry()
        self.setGeometry(vg)
        logger.info("Region selector opened: %dx%d at (%d,%d)",
                    vg.width(), vg.height(), vg.x(), vg.y())
        self.show()
        self.activateWindow()
        self.raise_()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.globalPos()
            self._current = event.globalPos()
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._current = event.globalPos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._selecting:
            self._selecting = False
            self.hide()

            x1 = min(self._origin.x(), self._current.x())
            y1 = min(self._origin.y(), self._current.y())
            x2 = max(self._origin.x(), self._current.x())
            y2 = max(self._origin.y(), self._current.y())
            w = x2 - x1
            h = y2 - y1

            if w > 10 and h > 10:
                self.region_selected.emit((x1, y1, w, h))
                logger.info("Region selected: (%d, %d, %d, %d)", x1, y1, w, h)
            else:
                self.selection_cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        # The widget's local coords start at (0,0) but map to virtual desktop.
        # We need to convert global coords to local for painting.
        vg = self.geometry()

        # Semi-transparent dark overlay over entire widget
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._selecting:
            # Convert global mouse coords to widget-local coords
            lx1 = min(self._origin.x(), self._current.x()) - vg.x()
            ly1 = min(self._origin.y(), self._current.y()) - vg.y()
            w = abs(self._current.x() - self._origin.x())
            h = abs(self._current.y() - self._origin.y())

            sel_rect = QRect(lx1, ly1, w, h)

            # Clear the selected area (show through)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(sel_rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw border
            pen = QPen(QColor(0, 120, 215), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(sel_rect)

            # Show dimensions
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(lx1 + 5, ly1 - 5, f"{w} x {h}")

        painter.end()
