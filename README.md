# ScreenTranslator

Real-time screen translator for Windows. Captures any region of your screen, detects text with Windows OCR, translates it using NLLB-200, and displays the translation as a transparent overlay.

![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

## How It Works

```
Screen Capture (mss/BetterCam)
       |
   Frame Diff (skip if unchanged)
       |
   Grayscale + threshold preprocessing (OpenCV)
       |
   WinRT OCR (Windows.Media.Ocr) ~30ms
       |
   Paragraph Merge (join multi-line blocks)
       |
   Style Extraction (detect text/bg colors)
       |
   Fuzzy cache lookup -> NLLB-200 Translation (600M, 200+ languages) ~2s on a cache miss
       |
   Transparent Overlay (PyQt5, click-through)
```

## Features

- **Windows OCR** — Uses the built-in `Windows.Media.Ocr` engine. Fast (~30ms), accurate, line-level detection with no model download needed.
- **200+ Languages** — Powered by Meta's NLLB-200 model via HuggingFace Transformers. Translates between any supported language pair.
- **Transparent Overlay** — Click-through overlay with auto-detected text/background colors. Two-pass rendering (backgrounds first, then text) prevents visual overlap.
- **Capture Modes** — Fullscreen, region selection (drag to draw), or window-specific capture.
- **Multi-monitor Capture** — Regions use absolute virtual-desktop coordinates; the capture engine works out which monitor a region is on and, with BetterCam, which DXGI device/output to use.
- **Smart Diffing** — Only re-processes when the screen content actually changes.
- **OCR Preprocessing** — Frames are converted to grayscale and thresholded before OCR; style (colour) extraction still uses the original frame.
- **Fuzzy Translation Cache** — LRU cache that also matches near-duplicate OCR output (Jaro + Sorensen-Dice similarity, threshold 0.65, 0.55 for CJK/Thai/etc.), so OCR jitter such as `l` vs `I` does not trigger a new translation. Entries expire after a few idle seconds (`cache_ttl_seconds`).
- **Flicker Suppression** — If a new translation is near-identical to one of the last few, the previous overlay is kept instead of redrawn.
- **Adaptive Polling** — The pipeline polls fast (~115 ms) while nothing is found, ~320 ms after a translation, and ~620 ms while text looks like it is being typed or scrolled.
- **Auto-clear** — The overlay is cleared after `auto_clear_delay_seconds` (default 5 s) without a new translation.
- **System Tray** — Runs in the background with global hotkeys.

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+T` | Toggle translation on/off |
| `Ctrl+Shift+R` | Select capture region |

## Installation

```bash
git clone https://github.com/Forkei/ScreenTranslator.git
cd ScreenTranslator
pip install -r requirements.txt
```

The NLLB-200 translation model (~2.4GB) downloads automatically on first run via HuggingFace.

## Usage

```bash
python -m src.main
```

1. The app starts in the system tray
2. Press `Ctrl+Shift+R` to select a screen region
3. Press `Ctrl+Shift+T` to start translating
4. Change source/target languages in Settings (right-click tray icon)

## Requirements

- Windows 10/11
- Python 3.10+
- ~3GB RAM (for the translation model)
- GPU optional (CUDA used automatically if available)

## Architecture

```
src/
  core/
    capture_engine.py    # Screen capture (mss + BetterCam fallback)
    frame_differ.py      # Skip unchanged frames
    ocr_engine.py        # WinRT OCR with paragraph merging
    pipeline.py          # Main capture->OCR->translate loop
    style_extractor.py   # Detect text/background colors from frame
    translation_engine.py # NLLB-200 via HuggingFace Transformers
    translation_cache.py # Fuzzy LRU cache with TTL and translation dedup
    text_similarity.py   # Jaro / Sorensen-Dice string similarity
  models/
    languages.py         # FLORES-200 + BCP-47 language mappings
    text_block.py        # Text block data model
    app_settings.py      # Application settings
  ui/
    overlay.py           # Transparent click-through overlay
    region_selector.py   # Draw-to-select capture region
    control_panel.py     # Main control panel
    settings_dialog.py   # Settings UI
    tray_icon.py         # System tray icon
  utils/
    model_downloader.py  # HuggingFace model download
    config_manager.py    # YAML config persistence
    window_utils.py      # Win32 window enumeration
test_fuzzy_cache.py      # Standalone checks for similarity, cache, TTL and dedup
```

## Configuration

Settings are stored in `config.yaml` in the working directory. It is created when you save settings in the app, is git-ignored, and falls back to defaults if missing. Cache and overlay behaviour can be tuned there (`cache_similarity_threshold`, `cache_ttl_seconds`, `auto_clear_delay_seconds`, ...).

## Tests

```bash
python test_fuzzy_cache.py
```

Runs plain assertions on the similarity functions, fuzzy cache, TTL expiry and translation dedup. It does not need the translation model or a GUI.

## Known Limitations

- **Translation speed** — ~2-3s per batch on CPU. GPU (CUDA) helps significantly.
- **Overlay visibility** — The overlay is excluded from screen capture to prevent feedback loops, but some capture tools may still pick it up.
- **Legacy settings** — `update_interval_ms` is still shown in the settings dialog but the pipeline now uses the adaptive polling intervals above. `model_name` / `model_dir` are unused because the model is loaded from the HuggingFace cache.
- **Local model quality** — NLLB-200 600M is decent but not as good as cloud APIs (Google Translate, DeepL). Trade-off for offline/private operation.

## Acknowledgments

- [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) by Meta AI — multilingual translation model
- [Windows.Media.Ocr](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr) — built-in Windows OCR engine
- Inspired by [Translumo](https://github.com/ramjke/Translumo)
