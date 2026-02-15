import logging
import os

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction

logger = logging.getLogger(__name__)

ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icon.png")


class TrayIcon(QSystemTrayIcon):
    """System tray icon with context menu for app control."""

    toggle_requested = pyqtSignal()
    region_select_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    show_panel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = False

        # Set icon
        if os.path.exists(ICON_PATH):
            self.setIcon(QIcon(ICON_PATH))
        else:
            # Use a default Qt icon
            from PyQt5.QtWidgets import QApplication
            self.setIcon(QApplication.style().standardIcon(
                QApplication.style().SP_ComputerIcon
            ))

        self.setToolTip("Screen Translator")

        self._setup_menu()
        self.activated.connect(self._on_activated)

    def _setup_menu(self):
        menu = QMenu()

        self.action_toggle = QAction("Start Translation", self)
        self.action_toggle.triggered.connect(self.toggle_requested.emit)
        menu.addAction(self.action_toggle)

        menu.addSeparator()

        action_region = QAction("Select Region", self)
        action_region.triggered.connect(self.region_select_requested.emit)
        menu.addAction(action_region)

        action_panel = QAction("Show Control Panel", self)
        action_panel.triggered.connect(self.show_panel_requested.emit)
        menu.addAction(action_panel)

        menu.addSeparator()

        action_settings = QAction("Settings", self)
        action_settings.triggered.connect(self.settings_requested.emit)
        menu.addAction(action_settings)

        menu.addSeparator()

        action_quit = QAction("Quit", self)
        action_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(action_quit)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_panel_requested.emit()

    def set_running(self, running: bool):
        self._is_running = running
        if running:
            self.action_toggle.setText("Stop Translation")
            self.setToolTip("Screen Translator - Active")
        else:
            self.action_toggle.setText("Start Translation")
            self.setToolTip("Screen Translator - Idle")
