import logging
import time
import traceback
import threading

from PyQt5.QtCore import QObject, pyqtSignal

from src.models.app_settings import AppSettings, CaptureMode
from src.models.text_block import TextBlock
from src.core.capture_engine import CaptureEngine
from src.core.frame_differ import FrameDiffer
from src.core.ocr_engine import OCREngine
from src.core.style_extractor import StyleExtractor
from src.core.translation_engine import TranslationEngine
from src.core.translation_cache import TranslationCache
from src.models.languages import flores_to_bcp47

logger = logging.getLogger(__name__)


class PipelineThread(QObject):
    """Runs capture->OCR->translate on a background thread.

    Heavy work (OCR ~150ms, translate ~300ms) runs off the main thread
    so the Qt UI stays responsive. Emits blocks_ready cross-thread via signal.
    """

    blocks_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings

        self.capture = CaptureEngine()
        self.differ = FrameDiffer(threshold=settings.frame_diff_threshold)
        self.ocr = OCREngine(confidence_threshold=settings.ocr_confidence_threshold)
        self.style_extractor = StyleExtractor()
        self.translation = TranslationEngine()
        self.cache = TranslationCache(max_size=settings.max_cache_size)

        self._running = False
        self._thread: threading.Thread | None = None
        self._last_blocks: list[TextBlock] = []
        self._null_frame_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def initialize(self, model_dir: str) -> None:
        """Initialize OCR and translation engines."""
        src = self.settings.source_language
        bcp47 = flores_to_bcp47(src) if src != "auto" else "en"
        if bcp47 is None:
            bcp47 = "en"
        self.ocr.initialize(language=bcp47)
        self.translation.load(model_dir)
        logger.info("Pipeline engines initialized")

    def start(self) -> None:
        """Start the pipeline on a background thread."""
        if self._running:
            return

        # (Re)start capture with current settings
        self.capture.stop()
        self.capture.start(monitor=self.settings.capture_monitor)
        self.differ.reset()
        self._null_frame_count = 0

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pipeline")
        self._thread.start()
        self.status_update.emit("Translation active")
        logger.info("Pipeline started (interval=%dms, monitor=%d, mode=%s)",
                    self.settings.update_interval_ms,
                    self.settings.capture_monitor,
                    self.settings.capture_mode.value)

    def stop(self) -> None:
        """Stop the pipeline (non-blocking)."""
        if not self._running:
            return
        self._running = False
        # Thread will exit on next loop check
        self.blocks_ready.emit([])
        self.status_update.emit("Translation stopped")
        logger.info("Pipeline stopped")

    def shutdown(self) -> None:
        """Full cleanup."""
        self.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.capture.stop()
        self.translation.unload()

    def update_settings(self, settings: AppSettings) -> None:
        """Apply new settings. Restarts capture if monitor/mode changed."""
        old_monitor = self.settings.capture_monitor
        old_mode = self.settings.capture_mode
        old_source = self.settings.source_language

        self.settings = settings
        self.differ.threshold = settings.frame_diff_threshold
        self.ocr.confidence_threshold = settings.ocr_confidence_threshold
        self.cache.max_size = settings.max_cache_size

        # Update OCR language if source language changed
        if settings.source_language != old_source and settings.source_language != "auto":
            self.ocr.set_language(settings.source_language)

        # Restart capture if monitor or mode changed
        if settings.capture_monitor != old_monitor or settings.capture_mode != old_mode:
            logger.info("Capture settings changed (monitor %d->%d, mode %s->%s), restarting capture",
                       old_monitor, settings.capture_monitor,
                       old_mode.value, settings.capture_mode.value)
            self.capture.stop()
            self.capture.start(monitor=settings.capture_monitor)
            self.differ.reset()

    def _loop(self) -> None:
        """Background thread loop: cycle + sleep."""
        logger.info("Pipeline thread started")
        while self._running:
            t0 = time.monotonic()
            try:
                self._run_cycle()
            except Exception as e:
                logger.error("Pipeline cycle error: %s\n%s", e, traceback.format_exc())
                self.error_occurred.emit(str(e))

            # Sleep for remaining interval
            elapsed_ms = (time.monotonic() - t0) * 1000
            sleep_ms = max(50, self.settings.update_interval_ms - elapsed_ms)
            time.sleep(sleep_ms / 1000)

        logger.info("Pipeline thread exited")

    def _run_cycle(self) -> None:
        """Execute one capture->OCR->translate cycle."""
        # 1. Capture
        region = None
        offset_x, offset_y = 0, 0

        if self.settings.capture_mode == CaptureMode.REGION and self.settings.capture_region:
            region = self.settings.capture_region
            offset_x, offset_y = region[0], region[1]
        elif self.settings.capture_mode == CaptureMode.WINDOW and self.settings.capture_window_title:
            from src.utils.window_utils import find_window_by_title, get_window_rect
            hwnd = find_window_by_title(self.settings.capture_window_title)
            if hwnd:
                rect = get_window_rect(hwnd)
                if rect:
                    region = rect
                    offset_x, offset_y = rect[0], rect[1]

        frame = self.capture.grab(
            mode=self.settings.capture_mode,
            region=region,
            monitor=self.settings.capture_monitor,
        )

        if frame is None:
            self._null_frame_count += 1
            if self._null_frame_count <= 3 or self._null_frame_count % 20 == 0:
                logger.warning("Capture returned None (count=%d)", self._null_frame_count)
            return

        if self._null_frame_count > 0:
            logger.info("Capture recovered after %d null frames", self._null_frame_count)
        self._null_frame_count = 0

        # 2. Frame diff — skip if unchanged
        if not self.differ.has_changed(frame):
            if self._last_blocks:
                self.blocks_ready.emit(self._last_blocks)
            return

        # Frame changed — clear stale overlay immediately so old text
        # doesn't linger at wrong positions while translation runs
        if self._last_blocks:
            self._last_blocks = []
            self.blocks_ready.emit([])

        # 3. OCR
        blocks = self.ocr.detect(frame, offset_x=offset_x, offset_y=offset_y)
        if not blocks:
            self._last_blocks = []
            self.blocks_ready.emit([])
            return

        logger.info("OCR: %d blocks detected", len(blocks))

        # 4. Style extraction (coords relative to frame)
        style_blocks = []
        for b in blocks:
            sb = TextBlock(
                x=b.x - offset_x, y=b.y - offset_y,
                width=b.width, height=b.height,
                text=b.text, confidence=b.confidence,
                font_size=b.font_size,
            )
            style_blocks.append(sb)

        self.style_extractor.extract(frame, style_blocks)

        for orig, styled in zip(blocks, style_blocks):
            orig.fg_color = styled.fg_color
            orig.bg_color = styled.bg_color

        # 5 & 6. Translation (with cache)
        src_lang = self.settings.source_language
        tgt_lang = self.settings.target_language
        effective_src = src_lang if src_lang != "auto" else "eng_Latn"

        to_translate = []
        translate_indices = []

        for i, block in enumerate(blocks):
            cached = self.cache.get(block.text, effective_src, tgt_lang)
            if cached is not None:
                block.translation = cached
            else:
                to_translate.append(block.text)
                translate_indices.append(i)

        if to_translate:
            logger.info("Translating %d texts (%s -> %s)", len(to_translate), effective_src, tgt_lang)
            translations = self.translation.translate_batch(
                to_translate,
                source_lang=effective_src,
                target_lang=tgt_lang,
            )
            for idx, trans in zip(translate_indices, translations):
                blocks[idx].translation = trans
                self.cache.put(blocks[idx].text, effective_src, tgt_lang, trans)
            logger.info("Translation complete")

        # 7. Emit to overlay
        self._last_blocks = blocks
        self.blocks_ready.emit(blocks)
