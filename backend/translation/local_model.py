"""Tier 3 of the Colombia product-name translation fallback chain (see
resolve.py) — a small, self-hosted machine translation model, not Claude.
Helsinki-NLP's opus-mt-es-en (~300MB, CPU-friendly): a dedicated
translation model, not a chat model, so there's no prompting here — raw
text in, translated text out. transformers/torch are imported lazily,
only inside this module, so the rest of the backend (which otherwise never
needs either) is unaffected if they're not installed; is_available() lets
resolve.py fall through to Tier 4 instead of erroring when they — or the
model weights, downloaded from the Hugging Face Hub and cached on first
use — aren't present yet.

Deliberately never treated as equivalent to a confirmed dictionary entry
— regional Colombian produce terms ("cidra", "cargamanto", "chontaduro")
are exactly the kind of term a general MT model is likely to get wrong (no
dictionary entry, easily confused with an unrelated word). Every result
from this module is tagged upstream as "unverified - needs review" (see
resolve.py and models.ProductTranslationSuggestion), never written
straight into the dictionary.
"""

import threading

MODEL_ID = 'Helsinki-NLP/opus-mt-es-en'
MAX_INPUT_CHARS = 200  # a product name, never a sentence — anything longer isn't this kind of input

_lock = threading.Lock()
_tokenizer = None
_model = None


def _load():
    global _tokenizer, _model
    with _lock:
        if _model is not None:
            return
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


def translate(text: str) -> str | None:
    """Best-effort English translation of a Spanish product name, or None
    if the model can't be loaded (transformers/torch not installed, no
    network for the first-run download, etc.) or produced nothing usable.
    Never raises — every caller treats None as a normal reason to fall
    through to Tier 4, not an error."""
    text = (text or '').strip()[:MAX_INPUT_CHARS]
    if not text:
        return None
    try:
        _load()
        inputs = _tokenizer(text, return_tensors='pt', truncation=True, max_length=64)
        generated = _model.generate(**inputs, max_new_tokens=40, num_beams=1)
        result = _tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        return result or None
    except Exception:
        return None
