import asyncio
import logging
import re

import cv2
import numpy as np

from src.models.text_block import TextBlock
from src.models.languages import flores_to_bcp47

logger = logging.getLogger(__name__)

try:
    from winrt.windows.media.ocr import OcrEngine as WinOcrEngine
    from winrt.windows.graphics.imaging import (
        BitmapDecoder,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.storage.streams import (
        InMemoryRandomAccessStream,
        DataWriter,
    )
    from winrt.windows.globalization import Language
    HAS_WINRT_OCR = True
except ImportError:
    HAS_WINRT_OCR = False
    logger.error("winrt OCR packages not installed")

# Minimum text length to bother translating
MIN_TEXT_LENGTH = 5


class OCREngine:
    """Text detection and recognition using Windows.Media.Ocr."""

    def __init__(self, confidence_threshold: float = 0.3):
        self.confidence_threshold = confidence_threshold
        self._engine = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_lang = None

    def initialize(self, language: str = "en") -> None:
        """Initialize the WinRT OCR engine for the given BCP-47 language tag."""
        if not HAS_WINRT_OCR:
            raise RuntimeError("winrt OCR packages are not installed")

        self._loop = asyncio.new_event_loop()
        self._create_engine(language)
        logger.info("OCR engine initialized (language=%s)", language)

    def _create_engine(self, bcp47: str) -> None:
        """Create a WinRT OcrEngine for the given BCP-47 tag."""
        try:
            lang = Language(bcp47)
            if WinOcrEngine.is_language_supported(lang):
                self._engine = WinOcrEngine.try_create_from_language(lang)
                self._current_lang = bcp47
                logger.info("WinRT OCR engine created for '%s'", bcp47)
                return
            else:
                logger.warning("Language '%s' not supported by Windows OCR", bcp47)
        except Exception as e:
            logger.warning("Failed to create OCR engine for '%s': %s", bcp47, e)

        # Fallback: user profile languages
        self._engine = WinOcrEngine.try_create_from_user_profile_languages()
        self._current_lang = bcp47
        if self._engine:
            logger.info("Using user profile OCR languages as fallback")
        else:
            raise RuntimeError("Could not create any WinRT OCR engine")

    def set_language(self, flores_code: str) -> None:
        """Switch OCR language. Accepts a FLORES-200 code."""
        bcp47 = flores_to_bcp47(flores_code)
        if bcp47 is None:
            logger.warning("No BCP-47 mapping for '%s', falling back to 'en'", flores_code)
            bcp47 = "en"

        if bcp47 == self._current_lang:
            return

        self._create_engine(bcp47)

    def detect(self, frame: np.ndarray, offset_x: int = 0, offset_y: int = 0) -> list[TextBlock]:
        """Run OCR on a frame and return detected text blocks."""
        if self._engine is None or self._loop is None:
            logger.error("OCR not initialized")
            return []

        try:
            lines = self._loop.run_until_complete(self._recognize_async(frame))
        except Exception as e:
            logger.error("OCR detection failed: %s", e)
            return []

        blocks = []
        for text, x, y, w, h in lines:
            text = text.strip()
            if not text or len(text) < MIN_TEXT_LENGTH:
                continue
            if re.fullmatch(r'[\d\s\.\,\;\:\!\?\-\—\–\|\@\#\$\%\^\&\*\(\)\[\]\{\}\/\\]+', text):
                continue
            if w < 5 or h < 5:
                continue

            font_size = max(8, int(h * 0.75))
            blocks.append(TextBlock(
                x=x + offset_x,
                y=y + offset_y,
                width=w,
                height=h,
                text=text,
                confidence=1.0,
                font_size=font_size,
            ))

        # Merge vertically adjacent lines into paragraphs
        merged = self._merge_paragraph_lines(blocks)

        for b in merged:
            logger.info("OCR block: %r", b.text[:80])
        logger.debug("OCR: %d lines -> %d blocks after paragraph merge", len(blocks), len(merged))
        return merged

    @staticmethod
    def _merge_paragraph_lines(blocks: list[TextBlock]) -> list[TextBlock]:
        """Merge vertically adjacent lines that form a paragraph.

        Lines are merged when they have similar x position and the vertical
        gap between them is small relative to line height.
        """
        if len(blocks) <= 1:
            return blocks

        # Sort by y position
        blocks.sort(key=lambda b: b.y)

        merged = []
        current = blocks[0]

        for next_block in blocks[1:]:
            gap = next_block.y - (current.y + current.height)
            line_h = current.height

            # Merge if: vertical gap < 1.5x line height AND left edges align within 30% of width
            x_diff = abs(next_block.x - current.x)
            same_paragraph = (
                gap < line_h * 1.5
                and x_diff < current.width * 0.3
            )

            if same_paragraph:
                # Merge: expand bbox, join text
                new_x = min(current.x, next_block.x)
                new_y = current.y
                new_x2 = max(current.x + current.width, next_block.x + next_block.width)
                new_y2 = next_block.y + next_block.height
                current = TextBlock(
                    x=new_x,
                    y=new_y,
                    width=new_x2 - new_x,
                    height=new_y2 - new_y,
                    text=current.text + " " + next_block.text,
                    confidence=1.0,
                    font_size=current.font_size,
                )
            else:
                merged.append(current)
                current = next_block

        merged.append(current)
        return merged

    async def _recognize_async(self, frame: np.ndarray) -> list[tuple[str, int, int, int, int]]:
        """Async WinRT OCR recognition. Returns list of (text, x, y, w, h)."""
        # Encode frame as BMP
        success, buf = cv2.imencode('.bmp', frame)
        if not success:
            logger.error("Failed to encode frame as BMP")
            return []

        bmp_bytes = buf.tobytes()

        # Write to InMemoryRandomAccessStream
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(bmp_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        # Decode bitmap
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        # Convert to BGRA8 if needed (WinRT OCR requires Gray8 or BGRA8)
        if bitmap.bitmap_pixel_format != BitmapPixelFormat.BGRA8:
            bitmap = SoftwareBitmap.convert(bitmap, BitmapPixelFormat.BGRA8)

        # Run OCR
        result = await self._engine.recognize_async(bitmap)

        # Extract lines with bounding boxes
        lines = []
        for line in result.lines:
            text = line.text
            if not text:
                continue

            # Compute bounding box from words
            min_x = min(w.bounding_rect.x for w in line.words)
            min_y = min(w.bounding_rect.y for w in line.words)
            max_x = max(w.bounding_rect.x + w.bounding_rect.width for w in line.words)
            max_y = max(w.bounding_rect.y + w.bounding_rect.height for w in line.words)

            lines.append((
                text,
                int(min_x),
                int(min_y),
                int(max_x - min_x),
                int(max_y - min_y),
            ))

        # Cleanup
        stream.close()

        return lines
