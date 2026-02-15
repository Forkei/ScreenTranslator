import logging

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QWidget, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QLineEdit, QLabel, QSlider, QGroupBox,
)

from src.models.app_settings import AppSettings, CaptureMode
from src.models.languages import get_all_languages, get_flores_code
from src.utils.window_utils import get_visible_windows

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Tabbed settings dialog for all app configuration."""

    settings_changed = pyqtSignal(object)  # AppSettings

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- Language tab ---
        lang_tab = QWidget()
        lang_layout = QFormLayout(lang_tab)

        self.combo_source = QComboBox()
        self.combo_source.addItem("Auto Detect", "auto")
        for name in get_all_languages():
            code = get_flores_code(name)
            if code:
                self.combo_source.addItem(name, code)
        lang_layout.addRow("Source Language:", self.combo_source)

        self.combo_target = QComboBox()
        for name in get_all_languages():
            code = get_flores_code(name)
            if code:
                self.combo_target.addItem(name, code)
        lang_layout.addRow("Target Language:", self.combo_target)

        self.tabs.addTab(lang_tab, "Language")

        # --- Capture tab ---
        cap_tab = QWidget()
        cap_layout = QFormLayout(cap_tab)

        self.combo_capture_mode = QComboBox()
        self.combo_capture_mode.addItem("Fullscreen", CaptureMode.FULLSCREEN.value)
        self.combo_capture_mode.addItem("Region", CaptureMode.REGION.value)
        self.combo_capture_mode.addItem("Window", CaptureMode.WINDOW.value)
        cap_layout.addRow("Capture Mode:", self.combo_capture_mode)

        self.spin_monitor = QSpinBox()
        self.spin_monitor.setRange(0, 10)
        cap_layout.addRow("Monitor:", self.spin_monitor)

        self.combo_window = QComboBox()
        self.combo_window.setEditable(True)
        self._refresh_windows()
        cap_layout.addRow("Window:", self.combo_window)

        btn_refresh = QPushButton("Refresh Windows")
        btn_refresh.clicked.connect(self._refresh_windows)
        cap_layout.addRow("", btn_refresh)

        self.tabs.addTab(cap_tab, "Capture")

        # --- Appearance tab ---
        appear_tab = QWidget()
        appear_layout = QFormLayout(appear_tab)

        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(10, 100)
        self.slider_opacity.setTickInterval(10)
        self.lbl_opacity = QLabel()
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.slider_opacity)
        opacity_row.addWidget(self.lbl_opacity)
        self.slider_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"{v}%")
        )
        appear_layout.addRow("Overlay Opacity:", opacity_row)

        self.edit_font = QLineEdit()
        appear_layout.addRow("Font Family:", self.edit_font)

        self.spin_min_font = QSpinBox()
        self.spin_min_font.setRange(4, 72)
        appear_layout.addRow("Min Font Size:", self.spin_min_font)

        self.spin_max_font = QSpinBox()
        self.spin_max_font.setRange(8, 200)
        appear_layout.addRow("Max Font Size:", self.spin_max_font)

        self.check_bg = QCheckBox("Show background behind text")
        appear_layout.addRow("", self.check_bg)

        self.tabs.addTab(appear_tab, "Appearance")

        # --- Performance tab ---
        perf_tab = QWidget()
        perf_layout = QFormLayout(perf_tab)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(100, 5000)
        self.spin_interval.setSuffix(" ms")
        self.spin_interval.setSingleStep(50)
        perf_layout.addRow("Update Interval:", self.spin_interval)

        self.dspin_diff_threshold = QDoubleSpinBox()
        self.dspin_diff_threshold.setRange(0.1, 50.0)
        self.dspin_diff_threshold.setSingleStep(0.5)
        perf_layout.addRow("Frame Diff Threshold:", self.dspin_diff_threshold)

        self.dspin_ocr_conf = QDoubleSpinBox()
        self.dspin_ocr_conf.setRange(0.0, 1.0)
        self.dspin_ocr_conf.setSingleStep(0.05)
        self.dspin_ocr_conf.setDecimals(2)
        perf_layout.addRow("OCR Confidence Min:", self.dspin_ocr_conf)

        self.spin_cache = QSpinBox()
        self.spin_cache.setRange(50, 10000)
        self.spin_cache.setSingleStep(50)
        perf_layout.addRow("Translation Cache Size:", self.spin_cache)

        self.tabs.addTab(perf_tab, "Performance")

        # --- Hotkeys tab ---
        hotkey_tab = QWidget()
        hotkey_layout = QFormLayout(hotkey_tab)

        self.edit_hk_toggle = QLineEdit()
        hotkey_layout.addRow("Toggle Translation:", self.edit_hk_toggle)

        self.edit_hk_region = QLineEdit()
        hotkey_layout.addRow("Select Region:", self.edit_hk_region)

        self.edit_hk_quit = QLineEdit()
        hotkey_layout.addRow("Quit App:", self.edit_hk_quit)

        note = QLabel("Format: <ctrl>+<shift>+t")
        note.setStyleSheet("color: gray; font-size: 11px;")
        hotkey_layout.addRow("", note)

        self.tabs.addTab(hotkey_tab, "Hotkeys")

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _refresh_windows(self):
        self.combo_window.clear()
        for w in get_visible_windows():
            self.combo_window.addItem(w["title"])

    def _load_settings(self):
        s = self.settings

        # Language
        self._set_combo_data(self.combo_source, s.source_language)
        self._set_combo_data(self.combo_target, s.target_language)

        # Capture
        self._set_combo_data(self.combo_capture_mode, s.capture_mode.value)
        self.spin_monitor.setValue(s.capture_monitor)
        if s.capture_window_title:
            self.combo_window.setCurrentText(s.capture_window_title)

        # Appearance
        self.slider_opacity.setValue(int(s.overlay_opacity * 100))
        self.lbl_opacity.setText(f"{int(s.overlay_opacity * 100)}%")
        self.edit_font.setText(s.font_family)
        self.spin_min_font.setValue(s.min_font_size)
        self.spin_max_font.setValue(s.max_font_size)
        self.check_bg.setChecked(s.show_background)

        # Performance
        self.spin_interval.setValue(s.update_interval_ms)
        self.dspin_diff_threshold.setValue(s.frame_diff_threshold)
        self.dspin_ocr_conf.setValue(s.ocr_confidence_threshold)
        self.spin_cache.setValue(s.max_cache_size)

        # Hotkeys
        self.edit_hk_toggle.setText(s.hotkey_toggle)
        self.edit_hk_region.setText(s.hotkey_region)
        self.edit_hk_quit.setText(s.hotkey_quit)

    def _save(self):
        s = self.settings

        s.source_language = self.combo_source.currentData() or "auto"
        s.target_language = self.combo_target.currentData() or "eng_Latn"

        mode_val = self.combo_capture_mode.currentData()
        s.capture_mode = CaptureMode(mode_val) if mode_val else CaptureMode.FULLSCREEN
        s.capture_monitor = self.spin_monitor.value()
        s.capture_window_title = self.combo_window.currentText() or None

        s.overlay_opacity = self.slider_opacity.value() / 100.0
        s.font_family = self.edit_font.text() or "Arial"
        s.min_font_size = self.spin_min_font.value()
        s.max_font_size = self.spin_max_font.value()
        s.show_background = self.check_bg.isChecked()

        s.update_interval_ms = self.spin_interval.value()
        s.frame_diff_threshold = self.dspin_diff_threshold.value()
        s.ocr_confidence_threshold = self.dspin_ocr_conf.value()
        s.max_cache_size = self.spin_cache.value()

        s.hotkey_toggle = self.edit_hk_toggle.text()
        s.hotkey_region = self.edit_hk_region.text()
        s.hotkey_quit = self.edit_hk_quit.text()

        self.settings_changed.emit(s)
        self.accept()

    def _set_combo_data(self, combo: QComboBox, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
