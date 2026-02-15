import logging
import os

from PyQt5.QtCore import QEvent, QMetaObject, Qt, Q_ARG
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from src.models.app_settings import AppSettings, CaptureMode
from src.utils.config_manager import ConfigManager
from src.utils.model_downloader import is_model_downloaded, download_model
from src.core.pipeline import PipelineThread
from src.ui.overlay import OverlayWindow
from src.ui.control_panel import ControlPanel
from src.ui.tray_icon import TrayIcon
from src.ui.region_selector import RegionSelector
from src.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

# Custom events for hotkey -> Qt thread communication
_TOGGLE_EVENT = QEvent.Type(QEvent.registerEventType())
_REGION_EVENT = QEvent.Type(QEvent.registerEventType())
_QUIT_EVENT = QEvent.Type(QEvent.registerEventType())


class _ToggleEvent(QEvent):
    def __init__(self):
        super().__init__(_TOGGLE_EVENT)


class _RegionEvent(QEvent):
    def __init__(self):
        super().__init__(_REGION_EVENT)


class _QuitEvent(QEvent):
    def __init__(self):
        super().__init__(_QUIT_EVENT)


class HotkeyAwareControlPanel(ControlPanel):
    """Control panel that handles custom hotkey events from global hotkeys."""

    def event(self, event):
        if event.type() == _TOGGLE_EVENT:
            self.toggle_requested.emit()
            return True
        elif event.type() == _REGION_EVENT:
            self.region_select_requested.emit()
            return True
        elif event.type() == _QUIT_EVENT:
            app = QApplication.instance()
            if app:
                app.quit()
            return True
        return super().event(event)


class AppController:
    """Main application controller — wires all components together."""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.settings = self.config_manager.load()

        self._model_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.settings.model_dir,
        )

        # UI components
        self.overlay = OverlayWindow()
        self.control_panel = HotkeyAwareControlPanel(
            source_lang=self.settings.source_language,
            target_lang=self.settings.target_language,
        )
        self.tray_icon = TrayIcon()
        self.region_selector = RegionSelector()

        # Pipeline (runs on background thread)
        self.pipeline = PipelineThread(self.settings)

        # Hotkey listener
        self._hotkey_listener = None

        self._connect_signals()

    def _connect_signals(self):
        """Wire all signals and slots."""
        # Pipeline -> Overlay
        self.pipeline.blocks_ready.connect(self.overlay.update_blocks)
        self.pipeline.error_occurred.connect(self._on_pipeline_error)

        # Control panel signals
        self.control_panel.toggle_requested.connect(self.toggle_translation)
        self.control_panel.source_changed.connect(self._on_source_changed)
        self.control_panel.target_changed.connect(self._on_target_changed)
        self.control_panel.settings_requested.connect(self.show_settings)
        self.control_panel.region_select_requested.connect(self.start_region_select)

        # Tray icon signals
        self.tray_icon.toggle_requested.connect(self.toggle_translation)
        self.tray_icon.region_select_requested.connect(self.start_region_select)
        self.tray_icon.settings_requested.connect(self.show_settings)
        self.tray_icon.quit_requested.connect(self.quit)
        self.tray_icon.show_panel_requested.connect(self._show_control_panel)

        # Region selector signals
        self.region_selector.region_selected.connect(self._on_region_selected)

    def start(self):
        """Initialize and show the app."""
        # Check for model
        if not is_model_downloaded(self._model_dir):
            self._download_model_with_dialog()

        # Initialize pipeline
        try:
            self.pipeline.initialize(self._model_dir)
        except Exception as e:
            logger.error("Pipeline init failed: %s", e)
            QMessageBox.critical(
                None, "Initialization Error",
                f"Failed to initialize translation pipeline:\n{e}\n\n"
                "Make sure all dependencies are installed and the model is downloaded."
            )
            return

        # Show UI
        self.tray_icon.show()
        self._show_control_panel()

        # Start global hotkeys
        self._start_hotkeys()

        logger.info("Application started")

    def toggle_translation(self):
        """Start or stop the translation pipeline."""
        if self.pipeline.is_running:
            self.pipeline.stop()
            self.overlay.clear()
            self.control_panel.set_running(False)
            self.tray_icon.set_running(False)
            logger.info("Translation stopped")
        else:
            self.overlay.set_font_family(self.settings.font_family)
            self.overlay.set_overlay_opacity(self.settings.overlay_opacity)
            self.overlay.set_show_background(self.settings.show_background)
            self.pipeline.start()
            self.control_panel.set_running(True)
            self.tray_icon.set_running(True)
            logger.info("Translation started")

    def start_region_select(self):
        """Open region selector overlay."""
        if self.pipeline.is_running:
            self.pipeline.stop()
            self.overlay.clear()
        self.region_selector.start_selection()

    def _on_region_selected(self, region: tuple):
        """Handle region selection."""
        self.settings.capture_mode = CaptureMode.REGION
        self.settings.capture_region = region
        self.pipeline.update_settings(self.settings)
        self.config_manager.save(self.settings)
        logger.info("Region set to %s", region)

    def _on_source_changed(self, code: str):
        self.settings.source_language = code
        self.pipeline.update_settings(self.settings)
        self.pipeline.cache.clear()

    def _on_target_changed(self, code: str):
        self.settings.target_language = code
        self.pipeline.update_settings(self.settings)
        self.pipeline.cache.clear()

    def show_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self.settings)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec_()

    def _on_settings_changed(self, new_settings: AppSettings):
        self.settings = new_settings
        self.pipeline.update_settings(self.settings)
        self.overlay.set_font_family(self.settings.font_family)
        self.overlay.set_overlay_opacity(self.settings.overlay_opacity)
        self.overlay.set_show_background(self.settings.show_background)
        self.config_manager.save(self.settings)

        # Restart hotkeys with new bindings
        self._stop_hotkeys()
        self._start_hotkeys()

        logger.info("Settings updated")

    def _on_pipeline_error(self, error: str):
        logger.error("Pipeline error: %s", error)

    def _show_control_panel(self):
        self.control_panel.show()
        self.control_panel.raise_()

    def _download_model_with_dialog(self):
        """Download model with a progress dialog."""
        progress = QProgressDialog(
            "Downloading translation model...\nThis may take a few minutes.",
            "Cancel", 0, 100,
        )
        progress.setWindowTitle("Downloading Model")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumWidth(400)
        progress.show()

        def on_progress(msg, pct):
            QMetaObject.invokeMethod(
                progress, "setValue",
                Qt.QueuedConnection,
                Q_ARG(int, int(pct * 100)),
            )
            QMetaObject.invokeMethod(
                progress, "setLabelText",
                Qt.QueuedConnection,
                Q_ARG(str, msg),
            )

        try:
            download_model(self._model_dir, progress_callback=on_progress)
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                None, "Download Failed",
                f"Failed to download translation model:\n{e}\n\n"
                "Check your internet connection and try again."
            )
            raise
        finally:
            progress.close()

    def _start_hotkeys(self):
        """Register global hotkeys using pynput."""
        try:
            from pynput import keyboard

            hotkeys = {
                self.settings.hotkey_toggle: lambda: QApplication.instance().postEvent(
                    self.control_panel, _ToggleEvent()
                ),
                self.settings.hotkey_region: lambda: QApplication.instance().postEvent(
                    self.control_panel, _RegionEvent()
                ),
                self.settings.hotkey_quit: lambda: QApplication.instance().postEvent(
                    self.control_panel, _QuitEvent()
                ),
            }

            self._hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self._hotkey_listener.start()
            logger.info("Global hotkeys registered")

        except Exception as e:
            logger.warning("Failed to register hotkeys: %s", e)

    def _stop_hotkeys(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    def quit(self):
        """Shutdown everything and quit."""
        logger.info("Shutting down...")
        self._stop_hotkeys()
        self.pipeline.shutdown()
        self.overlay.close()
        self.control_panel.close()
        self.tray_icon.hide()
        self.config_manager.save(self.settings)
        QApplication.instance().quit()
