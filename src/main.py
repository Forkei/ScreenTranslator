"""Screen Translator — Entry Point

Real-time screen translator overlay for Windows.
Captures screen, detects text via OCR, translates locally, and overlays results.
"""
import sys
import os
import logging

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def setup_logging():
    level = logging.DEBUG if "--debug" in sys.argv else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries at debug level
    if level == logging.DEBUG:
        logging.getLogger("PIL").setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.INFO)


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Screen Translator...")

    import signal
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer

    # High-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Screen Translator")
    app.setQuitOnLastWindowClosed(False)

    # Allow Ctrl+C to kill the app — Qt blocks SIGINT by default
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Timer lets Python process signals between Qt events
    _keepalive = QTimer()
    _keepalive.timeout.connect(lambda: None)
    _keepalive.start(200)

    from src.app import AppController

    controller = AppController()
    controller.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
