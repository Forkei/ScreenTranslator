import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FrameDiffer:
    """Detects whether the captured frame has changed enough to warrant re-OCR.

    Uses grayscale downsampled comparison with mean absolute difference.
    """

    def __init__(self, threshold: float = 5.0, downsample_width: int = 320):
        self.threshold = threshold
        self.downsample_width = downsample_width
        self._prev_frame: Optional[np.ndarray] = None

    def has_changed(self, frame: np.ndarray) -> bool:
        """Check if the frame differs significantly from the previous one.

        Args:
            frame: BGR numpy array

        Returns:
            True if frame changed or is the first frame
        """
        # Convert to grayscale and downsample
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        if w > self.downsample_width:
            scale = self.downsample_width / w
            new_h = int(h * scale)
            gray = cv2.resize(gray, (self.downsample_width, new_h), interpolation=cv2.INTER_AREA)

        if self._prev_frame is None:
            self._prev_frame = gray
            return True

        # Handle resolution changes
        if gray.shape != self._prev_frame.shape:
            self._prev_frame = gray
            return True

        diff = np.mean(np.abs(gray.astype(float) - self._prev_frame.astype(float)))
        self._prev_frame = gray

        changed = diff > self.threshold
        if not changed:
            logger.debug("Frame unchanged (diff=%.2f, threshold=%.2f)", diff, self.threshold)
        return changed

    def reset(self) -> None:
        """Reset the differ, forcing next frame to be treated as changed."""
        self._prev_frame = None
