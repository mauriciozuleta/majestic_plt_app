"""The weight of the usual RETAIL UNIT of fresh produce sold as a pack or a bunch, from a free table (data/retail_unit_weights.json): no AI, no network.

A catalog row priced per generic "unit" / "each" on raspberries is a clamshell, not one berry; asking for "one single whole item" (what the web research does, and what USDA's piece table
gives) returns 4 g and a price of 2,987 per kg. This table says what the unit usually weighs (6 oz = 170 g). It is a table of typical sizes, not a measurement, so every conversion that
uses it is labelled low confidence; a weight a person typed always wins over it. It only answers for generic count units (each / pack / bunch / head) on a single unit: "4 count bag" is a
count of pieces and stays with the piece weights."""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / 'data' / 'retail_unit_weights.json'
GENERIC_COUNT_UNITS = ('each', 'pack', 'bunch', 'head')


def _compile(words: list[str]):
    if not words:
        return None
    return re.compile(r'\b(?:' + '|'.join(re.escape(word) for word in sorted(words, key=len, reverse=True)) + r')(?:s|es)?\b', re.IGNORECASE)


@lru_cache(maxsize=1)
def _entries() -> list[dict]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [{**entry, 'match': _compile(entry['words']), 'exclude': _compile(entry.get('not', []))} for entry in data.get('entries', [])]


def lookup(name: str, count_unit: str | None = 'each', item_count: float | None = None) -> dict | None:
    """{kg, id, note} for the retail unit of this product, or None: not a pack / bunch commodity, a processed name, or a count of several pieces."""
    if count_unit not in GENERIC_COUNT_UNITS or (item_count not in (None, 1, 1.0)):
        return None
    from .hs import match_keyword_rule

    known = match_keyword_rule(name)  # the HS keyword rules know what the product is: only PRODUCE has a retail pack ("Cream Cheese Strawberry" is a cheese)
    if known is not None and known[0].get('family') != 'produce':
        return None
    text = re.sub(r'[^a-z0-9 ]+', ' ', re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', (name or '').lower()))
    if not text.strip():
        return None
    for entry in _entries():
        if entry['match'].search(text) and not (entry['exclude'] and entry['exclude'].search(text)):
            return {'kg': float(entry['kg']), 'id': entry['id'], 'note': entry['note']}
    return None
