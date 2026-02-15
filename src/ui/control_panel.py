import logging

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel, QSizePolicy,
)

from src.models.languages import get_all_languages, get_flores_code, get_language_name, FLORES_CODES

logger = logging.getLogger(__name__)


class ControlPanel(QWidget):
    """Floating draggable control bar: [Start/Stop] [Source ▼] → [Target ▼] [⚙]"""

    toggle_requested = pyqtSignal()
    source_changed = pyqtSignal(str)   # FLORES code
    target_changed = pyqtSignal(str)   # FLORES code
    settings_requested = pyqtSignal()
    region_select_requested = pyqtSignal()

    def __init__(self, source_lang: str = "auto", target_lang: str = "eng_Latn", parent=None):
        super().__init__(parent)
        self._drag_pos = QPoint()
        self._is_running = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedHeight(40)

        self._setup_ui(source_lang, target_lang)
        self._apply_style()

    def _setup_ui(self, source_lang: str, target_lang: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Start/Stop button
        self.btn_toggle = QPushButton("Start")
        self.btn_toggle.setFixedWidth(70)
        self.btn_toggle.clicked.connect(self._on_toggle)
        layout.addWidget(self.btn_toggle)

        # Source language combo
        self.combo_source = QComboBox()
        self.combo_source.setFixedWidth(160)
        self._populate_language_combo(self.combo_source, include_auto=True)
        self._set_combo_lang(self.combo_source, source_lang)
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)
        layout.addWidget(self.combo_source)

        # Arrow label
        arrow = QLabel("  ->  ")
        arrow.setAlignment(Qt.AlignCenter)
        layout.addWidget(arrow)

        # Target language combo
        self.combo_target = QComboBox()
        self.combo_target.setFixedWidth(160)
        self._populate_language_combo(self.combo_target, include_auto=False)
        self._set_combo_lang(self.combo_target, target_lang)
        self.combo_target.currentIndexChanged.connect(self._on_target_changed)
        layout.addWidget(self.combo_target)

        # Region select button
        self.btn_region = QPushButton("[ ]")
        self.btn_region.setFixedWidth(36)
        self.btn_region.setToolTip("Select Region")
        self.btn_region.clicked.connect(self.region_select_requested.emit)
        layout.addWidget(self.btn_region)

        # Settings button
        self.btn_settings = QPushButton("...")
        self.btn_settings.setFixedWidth(36)
        self.btn_settings.setToolTip("Settings")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.btn_settings)

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton#running {
                background-color: #c62828;
                color: white;
            }
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                color: #e0e0e0;
            }
            QComboBox::drop-down {
                border: none;
            }
            QLabel {
                color: #aaa;
            }
        """)

    def _populate_language_combo(self, combo: QComboBox, include_auto: bool):
        if include_auto:
            combo.addItem("Auto Detect", "auto")
        for lang_name in get_all_languages():
            code = get_flores_code(lang_name)
            if code:
                combo.addItem(lang_name, code)

    def _set_combo_lang(self, combo: QComboBox, lang_code: str):
        for i in range(combo.count()):
            if combo.itemData(i) == lang_code:
                combo.setCurrentIndex(i)
                return

    def _on_toggle(self):
        self.toggle_requested.emit()

    def _on_source_changed(self):
        code = self.combo_source.currentData()
        if code:
            self.source_changed.emit(code)

    def _on_target_changed(self):
        code = self.combo_target.currentData()
        if code:
            self.target_changed.emit(code)

    def set_running(self, running: bool):
        """Update the toggle button state."""
        self._is_running = running
        if running:
            self.btn_toggle.setText("Stop")
            self.btn_toggle.setObjectName("running")
        else:
            self.btn_toggle.setText("Start")
            self.btn_toggle.setObjectName("")
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)

    # --- Dragging ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
