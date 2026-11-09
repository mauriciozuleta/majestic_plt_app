"""Spanish -> English product names for the catalogs that are not in English (Colombia's La Mayorista and Corabastos today).

This is the single source of the translation, shared by the whole app:
  1. user overrides   (table product_translation_overrides, confirmed in the Colombia product table) — they win, so a wrong dictionary entry can be corrected;
  2. the curated dictionary  data/product_translations_es_en.json — built from the canonical name reference of both Colombian catalogs, with deliberate
     disambiguations (Aji = chili pepper, Pimenton = bell pepper ...); the frontend (productTranslations.js) imports the SAME file;
  3. a fuzzy match (Levenshtein similarity >= 0.85) of the normalized name against every known key: "Tomate Chonto Extra" -> "Tomate Chonto".
A name that misses all three stays Spanish and is flagged `translated: False` — never guessed here (the local-model / web-search suggestions of backend/translation/
remain a human-confirmed step and end up in the overrides table).

The key normalization is the same as the frontend's normalizeProductName: lowercase, accents stripped, "(parenthetical notes)" removed, single spaces."""

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / 'data' / 'product_translations_es_en.json'
FUZZY_MATCH_THRESHOLD = 0.85


@dataclass
class Translation:
    text: str  # the English name, or the Spanish one when there is none
    translated: bool
    tier: str  # 'override' | 'dictionary' | 'fuzzy' | 'none'
    matched_key: str | None = None


def normalize_name(name_es: str) -> str:
    text = unicodedata.normalize('NFD', (name_es or '').lower())
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'\([^)]*\)', '', text)
    return re.sub(r'\s+', ' ', text).strip()


@lru_cache(maxsize=1)
def dictionary() -> dict[str, str]:
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


def _levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(previous[j - 1] if char_a == char_b else 1 + min(previous[j - 1], previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def _similarity(a: str, b: str) -> float:
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1 - _levenshtein(a, b) / longest


def translate_name(name_es: str, overrides: dict[str, str] | None = None) -> Translation:
    """`overrides` maps a normalized key to the user's English name (see overrides_from_db)."""
    overrides = overrides or {}
    key = normalize_name(name_es)
    if key in overrides:
        return Translation(overrides[key], True, 'override', key)
    if key in dictionary():
        return Translation(dictionary()[key], True, 'dictionary', key)
    best_key, best_ratio = None, FUZZY_MATCH_THRESHOLD
    for candidate in [*dictionary().keys(), *overrides.keys()]:
        ratio = _similarity(key, candidate)
        if ratio >= best_ratio:
            best_key, best_ratio = candidate, ratio
    if best_key is not None:
        return Translation(overrides.get(best_key) or dictionary()[best_key], True, 'fuzzy', best_key)
    return Translation(name_es, False, 'none')


def overrides_from_db(db) -> dict[str, str]:
    from .. import models

    return {row.product_key: row.translation_en for row in db.query(models.ProductTranslationOverride).all()}
