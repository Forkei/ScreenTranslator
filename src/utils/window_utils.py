import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 not available, window capture disabled")


def get_visible_windows() -> list[dict]:
    """Return list of visible windows with titles and rects.

    Each dict: {"hwnd": int, "title": str, "rect": (x, y, w, h)}
    """
    if not HAS_WIN32:
        return []

    windows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y, x2, y2 = rect
            w, h = x2 - x, y2 - y
            if w > 0 and h > 0:
                windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "rect": (x, y, w, h),
                })
        except Exception:
            pass

    try:
        win32gui.EnumWindows(callback, None)
    except Exception as e:
        logger.error("Failed to enumerate windows: %s", e)

    return windows


def get_window_rect(hwnd: int) -> Optional[tuple]:
    """Get (x, y, w, h) for a window handle."""
    if not HAS_WIN32:
        return None
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y, x2, y2 = rect
        return (x, y, x2 - x, y2 - y)
    except Exception as e:
        logger.error("Failed to get window rect: %s", e)
        return None


def find_window_by_title(title: str) -> Optional[int]:
    """Find a window handle by partial title match."""
    if not HAS_WIN32:
        return None
    windows = get_visible_windows()
    for w in windows:
        if title.lower() in w["title"].lower():
            return w["hwnd"]
    return None
