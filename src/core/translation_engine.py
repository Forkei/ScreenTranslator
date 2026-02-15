import logging
from typing import Optional

import torch

logger = logging.getLogger(__name__)

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.error("transformers not installed")


MODEL_NAME = "facebook/nllb-200-distilled-600M"


class TranslationEngine:
    """Translates text using NLLB-200 via HuggingFace Transformers."""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._current_src_lang: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, model_dir: str) -> None:
        """Load the NLLB model and tokenizer.

        Args:
            model_dir: Ignored (kept for API compat). Model loads from HF cache.
        """
        if not HAS_TRANSFORMERS:
            raise RuntimeError("transformers is not installed")

        logger.info("Loading NLLB translation model (%s)...", MODEL_NAME)

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, src_lang="eng_Latn")
        self._model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME).to(self._device)
        self._model.eval()
        self._current_src_lang = "eng_Latn"
        logger.info("Translation device: %s", self._device)

        self._loaded = True
        logger.info("Translation model loaded successfully")

    def unload(self) -> None:
        """Unload model to free memory."""
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def translate(
        self,
        text: str,
        source_lang: str = "eng_Latn",
        target_lang: str = "fra_Latn",
    ) -> str:
        """Translate a single text string."""
        results = self.translate_batch([text], source_lang, target_lang)
        return results[0] if results else text

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "eng_Latn",
        target_lang: str = "fra_Latn",
    ) -> list[str]:
        """Translate multiple texts in a batch."""
        if not self._loaded:
            return texts
        if not texts:
            return []

        try:
            # Update source language if changed
            if source_lang != self._current_src_lang:
                self._tokenizer.src_lang = source_lang
                self._current_src_lang = source_lang

            target_token_id = self._tokenizer.convert_tokens_to_ids(target_lang)

            with torch.inference_mode():
                inputs = self._tokenizer(
                    texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=128,
                )
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
                translated = self._model.generate(
                    **inputs,
                    forced_bos_token_id=target_token_id,
                    max_new_tokens=128,
                )
                results = self._tokenizer.batch_decode(translated, skip_special_tokens=True)

            for i, (src, tgt) in enumerate(zip(texts, results)):
                logger.info("Translation [%s] -> [%s]", src[:60], tgt[:60])

            return results

        except Exception as e:
            logger.error("Batch translation failed: %s", e)
            return texts
