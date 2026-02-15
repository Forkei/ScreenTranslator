import logging

logger = logging.getLogger(__name__)

MODEL_NAME = "facebook/nllb-200-distilled-600M"


def is_model_downloaded(model_dir: str) -> bool:
    """Check if the NLLB model is available in HuggingFace cache."""
    try:
        from huggingface_hub import try_to_load_from_cache
        # Check if the main config file is cached
        result = try_to_load_from_cache(MODEL_NAME, "config.json")
        return result is not None and isinstance(result, str)
    except Exception:
        return False


def download_model(model_dir: str, progress_callback=None) -> None:
    """Download NLLB model and tokenizer to HuggingFace cache.

    Args:
        model_dir: Ignored (kept for API compat). Model uses HF cache.
        progress_callback: Optional callable(message: str, progress: float 0-1)
    """
    from huggingface_hub import snapshot_download

    def report(msg, pct):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg, pct)

    report("Downloading NLLB-200 600M translation model...", 0.0)

    try:
        snapshot_download(repo_id=MODEL_NAME)
        report("Model download complete!", 1.0)
    except Exception as e:
        logger.error("Model download failed: %s", e)
        raise
