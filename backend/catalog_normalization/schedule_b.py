"""The US Census Schedule B in the app (backend/comtrade/data/schedule_b.json, built by build_schedule_b.py from the chapter files, 96 of the 97 chapters; chapters 1 and 72 are plain
text without the structured tables and are not included, 77 is reserved).

Schedule B is the US export classification built on the HS: its first six digits ARE the HS 2022 code. What it adds over the Comtrade reference is the 10-digit statistical line under each
six-digit code ("0702.00.0015 Cherry tomatoes, certified organic") and the unit of quantity the Census asks for (kg, No., liters ...).

Tried and NOT wired in (2026-11-12): a free text match of product names against these descriptions as a backup before Claude. On the 1,287 stored food names the keyword rules do not
cover it answered 110 and agreed with the stored code on 56 (about half), and its mistakes were wild (beef strip loin -> 050400 guts). Words alone cannot tell "beef" from "beef sausage";
the keyword rules (hs.py) stay the free tier.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / 'comtrade' / 'data' / 'schedule_b.json'


@lru_cache(maxsize=1)
def _lines() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding='utf-8'))['lines']
    except (OSError, ValueError, KeyError):
        return []


@lru_cache(maxsize=1)
def _by_hs6() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for line in _lines():
        grouped.setdefault(line['code'][:6], []).append(line)
    return grouped


def lines_for(code: str | None) -> list[dict]:
    """The 10-digit Schedule B lines under a 4- or 6-digit code (or the one line of a 10-digit code): [{code, description, path, unit, unit2}]. [] when unknown."""
    code = re.sub(r'\D', '', code or '')
    if len(code) == 10:
        return [line for line in _by_hs6().get(code[:6], []) if line['code'] == code]
    if len(code) == 6:
        return list(_by_hs6().get(code, []))
    if len(code) == 4:
        return [line for line in _lines() if line['code'].startswith(code)]
    return []


def unit_for(code: str | None) -> tuple[str | None, str | None]:
    """(unit, second unit) of quantity the Census asks for under a code; the first line's when a 4- or 6-digit code has several. (None, None) when unknown."""
    lines = lines_for(code)
    return (lines[0]['unit'], lines[0]['unit2']) if lines else (None, None)


# ---------------------------------------------------------------- text search over the descriptions
import math
from collections import Counter, defaultdict

SEARCH_LAST_CHAPTER = 24
EXTRA_HEADINGS = ('2501',)  # salt: the only edible heading outside chapters 1-24
STOP = {'and', 'or', 'of', 'the', 'a', 'an', 'in', 'for', 'to', 'with', 'than', 'not', 'other', 'others', 'whether', 'fresh', 'chilled', 'nes', 'nesoi', 'including', 'its', 'by', 'from',
        'on', 'as', 'at', 'is', 'are', 'be', 'that', 'this', 'which', 'only', 'kg', 'g', 'lb', 'lbs', 'oz', 'pack', 'pk', 'ct', 'each', 'ml', 'bag', 'jug', 'bottle', 'sack', 'regular',
        'style', 'variety', 'brand', 'packaged', 'imported', 'local', 'regional', 'name', 'liter', 'gallon', 'pound', 'arroba', 'by'}


def _stem(word: str) -> str:
    for suffix, cut in (('ies', 'y'), ('oes', 'o'), ('ses', 's'), ('es', ''), ('s', '')):
        if len(word) > len(suffix) + 2 and word.endswith(suffix) and not word.endswith(('ss', 'us')):
            return word[: -len(suffix)] + cut
    return word


def tokens(text: str) -> list[str]:
    return [_stem(word) for word in re.findall(r'[a-z]+', (text or '').lower()) if word not in STOP and len(word) > 1]


@lru_cache(maxsize=1)
def _index() -> dict:
    texts: dict[str, list[str]] = defaultdict(list)
    for line in _lines():
        code6 = line['code'][:6]
        if int(code6[:2]) > SEARCH_LAST_CHAPTER and code6[:4] not in EXTRA_HEADINGS:
            continue
        for part in [piece.strip() for piece in (line['path'] or '').split('>')] + [line['description']]:
            if part and part not in texts[code6]:
                texts[code6].append(part)
    docs = {code: Counter(tokens(' '.join(parts))) for code, parts in texts.items()}
    frequency = Counter(token for doc in docs.values() for token in doc)
    idf = {token: math.log(1 + len(docs) / count) for token, count in frequency.items()}
    return {'docs': docs, 'idf': idf, 'texts': {code: ' > '.join(parts) for code, parts in texts.items()}}


def search(name: str, limit: int = 5, within: str = '') -> list[dict]:
    """The six-digit codes whose Schedule B text holds the most (idf-weighted) of the name's words: [{code, score, text}], best first; `within` keeps only the codes that start with it (a heading). Words the Schedule B never uses (brands) are ignored."""
    index = _index()
    known = [token for token in set(tokens(re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', name or ''))) if token in index['idf']]
    total = sum(index['idf'][token] for token in known)
    if not total:
        return []
    ranked = []
    for code, doc in index['docs'].items():
        if not code.startswith(within):
            continue
        hit = sum(index['idf'][token] for token in known if token in doc)
        if hit:
            ranked.append({'code': code, 'score': round(hit / total, 3), 'text': index['texts'][code]})
    ranked.sort(key=lambda row: (-row['score'], len(row['text']), row['code']))
    return ranked[:limit]
