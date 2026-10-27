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


def _get_monitor_geometries() -> list[dict]:
    """Return monitor geometries as [{"left", "top", "width", "height"}, ...].

    Uses mss (which queries the OS).  mss.monitors[0] is the virtual desktop;
    [1..N] are real monitors.  The returned list is indexed 0..N-1.
    """
    if not HAS_MSS:
        return []
    try:
        with mss.mss() as sct:
            return [
                {"left": m["left"], "top": m["top"],
                 "width": m["width"], "height": m["height"]}
                for m in sct.monitors[1:]
            ]
    except Exception as e:
        logger.warning("Failed to enumerate monitors: %s", e)
        return []


def _build_bettercam_map(monitors: list[dict]) -> dict[int, tuple[int, int]]:
    """Build a mapping from mss monitor index -> (device_idx, output_idx).

    BetterCam uses DXGI adapter (device) and output indices which don't
    necessarily match the OS monitor order — e.g. two monitors on separate
    GPUs are both output_idx=0 on different device_idx values.

    We probe all (device, output) pairs, grab a frame to get the resolution,
    then match to the mss monitor list by (width, height).
    """
    if not HAS_BETTERCAM or not monitors:
        return {}

    # Collect all valid (device, output) -> (width, height)
    bc_outputs: list[tuple[int, int, int, int]] = []  # (dev, out, w, h)
    for dev in range(8):
        for out in range(8):
            try:
                cam = bettercam.create(device_idx=dev, output_idx=out, output_color="BGR")
                frame = cam.grab()
                if frame is not None:
                    f = np.array(frame)
                    bc_outputs.append((dev, out, f.shape[1], f.shape[0]))
                cam.stop()
                del cam
            except Exception:
                if out == 0:
                    break  # No more devices
                break  # No more outputs on this device

    # Match each mss monitor to a BetterCam output by resolution.
    # Use a consumed-set so each BetterCam output is assigned at most once.
    mapping: dict[int, tuple[int, int]] = {}
    used: set[int] = set()

    for mon_idx, mon in enumerate(monitors):
        mw, mh = mon["width"], mon["height"]
        for bc_idx, (dev, out, bw, bh) in enumerate(bc_outputs):
            if bc_idx in used:
                continue
            if bw == mw and bh == mh:
                mapping[mon_idx] = (dev, out)
                used.add(bc_idx)
                logger.info("Monitor %d (%dx%d at %d,%d) -> BetterCam device=%d output=%d",
                            mon_idx, mw, mh, mon["left"], mon["top"], dev, out)
                break

    return mapping


class CaptureEngine:
    """Captures screen frames using BetterCam (preferred) or mss (fallback).

    Region coordinates are always *absolute virtual-desktop* coordinates
    (the same coordinate space the OS and Qt use).  This class transparently
    resolves which physical monitor a region lives on, converts to
    monitor-local coordinates, and switches BetterCam to the correct
    DXGI device/output.

    Thread-safety: mss uses thread-local device contexts, so the mss instance
    must be created on the same thread that calls grab(). We handle this by
    lazily creating the instance on first grab().
    """

    def __init__(self):
        self._camera = None
        self._use_bettercam = HAS_BETTERCAM
        self._monitor = 0           # current mss monitor index
        self._bc_device = 0          # current BetterCam device_idx
        self._bc_output = 0          # current BetterCam output_idx
        self._started = False
        self._monitors: list[dict] = []
        self._bc_map: dict[int, tuple[int, int]] = {}  # mss idx -> (dev, out)
        self._local = threading.local()

    def start(self, monitor: int = 0) -> None:
        """Configure the capture backend. Actual mss init is deferred to grab()."""
        self._monitor = monitor
        self._monitors = _get_monitor_geometries()

        if self._use_bettercam:
            # Build the device/output mapping once
            self._bc_map = _build_bettercam_map(self._monitors)
            dev, out = self._bc_map.get(monitor, (0, 0))
            try:
                self._camera = bettercam.create(
                    device_idx=dev, output_idx=out, output_color="BGR",
                )
                self._bc_device = dev
                self._bc_output = out
                logger.info("BetterCam capture created for monitor %d (device=%d, output=%d)",
                            monitor, dev, out)
                self._started = True
                return
            except Exception as e:
                logger.warning("BetterCam init failed: %s, falling back to mss", e)
                self._use_bettercam = False
                self._camera = None

        if HAS_MSS:
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

    # ------------------------------------------------------------------
    # Monitor resolution helpers
    # ------------------------------------------------------------------

    def _find_monitor_for_region(self, region: tuple) -> tuple[int, tuple]:
        """Determine which monitor an absolute region falls on.

        Returns (monitor_idx, local_region) where local_region has coords
        relative to that monitor's origin.
        """
        x, y, w, h = region
        cx, cy = x + w // 2, y + h // 2

        for idx, mon in enumerate(self._monitors):
            ml, mt = mon["left"], mon["top"]
            mr = ml + mon["width"]
            mb = mt + mon["height"]
            if ml <= cx < mr and mt <= cy < mb:
                local_region = (x - ml, y - mt, w, h)
                return idx, local_region

        # Fallback: keep current monitor
        logger.warning("Region center (%d,%d) not inside any known monitor, "
                       "falling back to monitor %d", cx, cy, self._monitor)
        if self._monitors:
            mon = self._monitors[self._monitor]
            local_region = (x - mon["left"], y - mon["top"], w, h)
            return self._monitor, local_region
        return self._monitor, region

    def _ensure_bettercam_monitor(self, monitor_idx: int) -> None:
        """Recreate the BetterCam camera if the target monitor changed."""
        if monitor_idx == self._monitor and self._camera is not None:
            return

        dev, out = self._bc_map.get(monitor_idx, (monitor_idx, 0))

        # Tear down old camera
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None
        try:
            self._camera = bettercam.create(
                device_idx=dev, output_idx=out, output_color="BGR",
            )
            self._monitor = monitor_idx
            self._bc_device = dev
            self._bc_output = out
            logger.info("BetterCam switched to monitor %d (device=%d, output=%d)",
                        monitor_idx, dev, out)
        except Exception as e:
            logger.error("Failed to create BetterCam for monitor %d (device=%d, output=%d): %s",
                         monitor_idx, dev, out, e)

    # ------------------------------------------------------------------
    # Grab
    # ------------------------------------------------------------------

    def grab(
        self,
        mode: CaptureMode = CaptureMode.FULLSCREEN,
        region: Optional[tuple] = None,
        monitor: int = 0,
    ) -> Optional[np.ndarray]:
        """Capture a frame. Returns BGR numpy array, or None on failure.

        *region* uses absolute virtual-desktop coordinates (x, y, w, h).
        """
        if not self._started:
            logger.error("Capture engine not started")
            return None

        try:
            if self._use_bettercam:
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
            target_monitor, local_region = self._find_monitor_for_region(region)
            self._ensure_bettercam_monitor(target_monitor)
            if self._camera is None:
                return None
            lx, ly, lw, lh = local_region
            frame = self._camera.grab(region=(lx, ly, lx + lw, ly + lh))
        else:
            if self._camera is None:
                return None
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
            idx = min(monitor + 1, len(monitors) - 1)
            mon = monitors[idx]

        screenshot = sct.grab(mon)
        frame = np.array(screenshot)
        # mss returns BGRA, convert to BGR
        return frame[:, :, :3]
