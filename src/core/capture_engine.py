import logging
import threading
from typing import Optional

import numpy as np

from src.models.app_settings import CaptureMode

logger = logging.getLogger(__name__)

try:
    import bettercam
    HAS_BETTERCAM = True
except ImportError:
    HAS_BETTERCAM = False
    logger.info("bettercam not available, using mss fallback")

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


class CaptureEngine:
    """Captures screen frames using BetterCam (preferred) or mss (fallback).

    Thread-safety: mss uses thread-local device contexts, so the mss instance
    must be created on the same thread that calls grab(). We handle this by
    lazily creating the instance on first grab().
    """

    def __init__(self):
        self._camera = None
        self._use_bettercam = HAS_BETTERCAM
        self._monitor = 0
        self._started = False
        # mss is thread-local — store per-thread instances
        self._local = threading.local()

    def start(self, monitor: int = 0) -> None:
        """Configure the capture backend. Actual mss init is deferred to grab()."""
        self._monitor = monitor

        if self._use_bettercam:
            try:
                self._camera = bettercam.create(output_idx=monitor, output_color="BGR")
                logger.info("BetterCam capture created for monitor %d", monitor)
                self._started = True
                return
            except Exception as e:
                logger.warning("BetterCam init failed: %s, falling back to mss", e)
                self._use_bettercam = False
                self._camera = None

        if HAS_MSS:
            # Don't create mss here — it must be created on the grab() thread
            self._started = True
            logger.info("mss capture configured for monitor %d (init deferred to grab thread)", monitor)
        else:
            raise RuntimeError("No screen capture backend available. Install bettercam or mss.")

    def stop(self) -> None:
        """Release capture resources."""
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None
        # Close any thread-local mss instance
        mss_inst = getattr(self._local, "mss_instance", None)
        if mss_inst is not None:
            try:
                mss_inst.close()
            except Exception:
                pass
            self._local.mss_instance = None
        self._started = False

    def _get_mss(self):
        """Get or create a thread-local mss instance."""
        inst = getattr(self._local, "mss_instance", None)
        if inst is None:
            inst = mss.mss()
            self._local.mss_instance = inst
            logger.info("mss instance created on thread %s", threading.current_thread().name)
        return inst

    def grab(
        self,
        mode: CaptureMode = CaptureMode.FULLSCREEN,
        region: Optional[tuple] = None,
        monitor: int = 0,
    ) -> Optional[np.ndarray]:
        """Capture a frame. Returns BGR numpy array, or None on failure."""
        if not self._started:
            logger.error("Capture engine not started")
            return None

        try:
            if self._use_bettercam and self._camera is not None:
                return self._grab_bettercam(mode, region)
            elif HAS_MSS:
                return self._grab_mss(mode, region, monitor)
            else:
                logger.error("No capture backend available")
                return None
        except Exception as e:
            logger.error("Capture failed: %s", e)
            return None

    def _grab_bettercam(self, mode: CaptureMode, region: Optional[tuple]) -> Optional[np.ndarray]:
        if mode == CaptureMode.REGION and region:
            x, y, w, h = region
            frame = self._camera.grab(region=(x, y, x + w, y + h))
        else:
            frame = self._camera.grab()

        if frame is None:
            return None
        return np.array(frame)

    def _grab_mss(self, mode: CaptureMode, region: Optional[tuple], monitor: int) -> Optional[np.ndarray]:
        sct = self._get_mss()

        if mode == CaptureMode.REGION and region:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": w, "height": h}
        else:
            monitors = sct.monitors
            idx = min(monitor + 1, len(monitors) - 1)  # mss monitors[0] is "all"
            mon = monitors[idx]

        screenshot = sct.grab(mon)
        frame = np.array(screenshot)
        # mss returns BGRA, convert to BGR
        return frame[:, :, :3]
