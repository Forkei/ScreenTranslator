from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CaptureMode(Enum):
    FULLSCREEN = "fullscreen"
    REGION = "region"
    WINDOW = "window"


@dataclass
class AppSettings:
    """Application settings persisted to config.yaml."""
    # Language settings
    source_language: str = "auto"    # "auto" for auto-detect, or FLORES code
    target_language: str = "eng_Latn"  # FLORES-200 code

    # Capture settings
    capture_mode: CaptureMode = CaptureMode.FULLSCREEN
    capture_region: Optional[tuple] = None   # (x, y, w, h) for region mode
    capture_window_title: Optional[str] = None  # Window title for window mode
    capture_monitor: int = 0                 # Monitor index for fullscreen

    # Performance settings
    update_interval_ms: int = 500    # Pipeline cycle interval
    frame_diff_threshold: float = 5.0  # Mean pixel diff to trigger re-OCR
    ocr_confidence_threshold: float = 0.3  # Min confidence to keep text block
    max_cache_size: int = 500        # Translation cache entries
    cache_similarity_threshold: float = 0.65  # Fuzzy cache match threshold
    cache_ttl_seconds: float = 3.0   # Cache TTL (clear after N seconds idle)
    auto_clear_delay_seconds: float = 5.0  # Auto-clear overlay after N seconds

    # Appearance settings
    overlay_opacity: float = 0.9     # Background rect opacity
    font_family: str = "Arial"
    min_font_size: int = 8
    max_font_size: int = 72
    show_background: bool = True     # Show background rect behind translated text

    # Hotkeys
    hotkey_toggle: str = "<ctrl>+<shift>+t"
    hotkey_region: str = "<ctrl>+<shift>+r"
    hotkey_quit: str = "<ctrl>+<shift>+q"

    # Model settings
    model_name: str = "ct2-nllb-200-distilled-600M-int8"
    model_dir: str = "models"

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, CaptureMode):
                d[k] = v.value
            elif isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """Deserialize from dict loaded from YAML."""
        settings = cls()
        for k, v in data.items():
            if not hasattr(settings, k):
                continue
            if k == "capture_mode":
                setattr(settings, k, CaptureMode(v))
            elif k == "capture_region" and v is not None:
                setattr(settings, k, tuple(v))
            else:
                setattr(settings, k, v)
        return settings
