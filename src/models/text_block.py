from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextBlock:
    """Represents a detected text region with its visual properties and translation."""
    # Bounding box: (x, y, width, height) in screen coordinates
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    # Original detected text
    text: str = ""

    # Translated text
    translation: str = ""

    # Visual properties
    fg_color: tuple = (255, 255, 255)  # (R, G, B) foreground/text color
    bg_color: tuple = (0, 0, 0)        # (R, G, B) background color
    font_size: int = 14

    # Confidence from OCR (0.0 - 1.0)
    confidence: float = 0.0

    @property
    def bbox(self) -> tuple:
        """Return (x, y, w, h) tuple."""
        return (self.x, self.y, self.width, self.height)

    @property
    def display_text(self) -> str:
        """Return translation if available, otherwise original text."""
        return self.translation if self.translation else self.text
