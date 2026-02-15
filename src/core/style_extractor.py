import logging

import cv2
import numpy as np

from src.models.text_block import TextBlock

logger = logging.getLogger(__name__)


class StyleExtractor:
    """Extracts foreground/background colors from text block regions using k-means."""

    def extract(self, frame: np.ndarray, blocks: list[TextBlock]) -> list[TextBlock]:
        """Extract text and background colors for each block from the frame.

        Samples border pixels around the block to determine the true page
        background, then uses k-means to find the foreground color that
        contrasts most with that background.

        Args:
            frame: BGR numpy array (full frame or region)
            blocks: List of TextBlock with bbox set

        Returns:
            Same blocks with fg_color and bg_color updated
        """
        h_frame, w_frame = frame.shape[:2]

        for block in blocks:
            try:
                margin = max(4, block.height // 2)

                # Expanded ROI clamped to frame bounds
                x1 = max(0, block.x - margin)
                y1 = max(0, block.y - margin)
                x2 = min(w_frame, block.x + block.width + margin)
                y2 = min(h_frame, block.y + block.height + margin)

                if x2 <= x1 or y2 <= y1:
                    continue

                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue

                # Sample border strips (top, bottom, left, right edges)
                strip = max(2, margin // 2)
                roi_h, roi_w = roi.shape[:2]
                border_pixels = []

                if strip < roi_h:
                    border_pixels.append(roi[:strip, :].reshape(-1, 3))   # top
                    border_pixels.append(roi[-strip:, :].reshape(-1, 3))  # bottom
                if strip < roi_w:
                    border_pixels.append(roi[:, :strip].reshape(-1, 3))   # left
                    border_pixels.append(roi[:, -strip:].reshape(-1, 3))  # right

                if border_pixels:
                    border_arr = np.concatenate(border_pixels, axis=0).astype(np.float32)
                    # Median of border pixels = page background
                    bg_bgr = np.median(border_arr, axis=0)
                else:
                    bg_bgr = np.array([255.0, 255.0, 255.0])

                # Inner ROI for k-means (original block area within expanded ROI)
                inner_x1 = block.x - x1
                inner_y1 = block.y - y1
                inner_x2 = inner_x1 + block.width
                inner_y2 = inner_y1 + block.height
                inner_x1 = max(0, inner_x1)
                inner_y1 = max(0, inner_y1)
                inner_x2 = min(roi_w, inner_x2)
                inner_y2 = min(roi_h, inner_y2)

                inner_roi = roi[inner_y1:inner_y2, inner_x1:inner_x2]
                pixels = inner_roi.reshape(-1, 3).astype(np.float32)

                if len(pixels) < 2:
                    continue

                # k-means with k=2
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
                _, labels, centers = cv2.kmeans(
                    pixels, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS
                )

                # Pick foreground as the cluster most different from border bg
                dist_0 = np.linalg.norm(centers[0] - bg_bgr)
                dist_1 = np.linalg.norm(centers[1] - bg_bgr)

                if dist_0 > dist_1:
                    fg_bgr = centers[0]
                else:
                    fg_bgr = centers[1]

                # Convert BGR to RGB tuples
                block.bg_color = (int(bg_bgr[2]), int(bg_bgr[1]), int(bg_bgr[0]))
                block.fg_color = (int(fg_bgr[2]), int(fg_bgr[1]), int(fg_bgr[0]))

            except Exception as e:
                logger.debug("Style extraction failed for block '%s': %s", block.text[:20], e)

        return blocks
