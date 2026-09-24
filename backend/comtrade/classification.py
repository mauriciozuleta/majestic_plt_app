"""HS commodity-code names for the Global Trade Data module, resolved
server-side because Comtrade's own `cmdDesc` field on the actual trade-data
endpoint is unreliable — blank/null in practice, confirmed against live
responses.

Single source of truth: Comtrade's own "Combined HS" classification
reference (`HS.json`), which merges every HS revision (H0 through H6) into
one lookup — necessary because the trade-data endpoint itself reports under
different revisions depending on the year (a 2024 query comes back tagged
`classificationCode: "H6"`, a 2022 query `"H5"`; a single fixed revision
file would silently miss codes introduced in whichever revision it wasn't
built from). This covers all HS codes at all levels (2-digit chapter,
4-digit heading, 6-digit subheading) for every traded good, not just food —
there is no chapter allow-list here.

Fetched once and cached to disk (~2MB); refreshed automatically once the
cache is more than a week old (HS nomenclature revisions happen roughly
every 5 years, so this is generous, not aggressive) — a failed refresh
falls back to the existing cache rather than leaving the app without names,
same as a failed fetch on an empty cache falls back to a generic label.
"""

import json
import time
from pathlib import Path

import httpx

REFERENCE_URL = 'https://comtradeapi.un.org/files/v1/app/reference/HS.json'
# Gitignored, like the other fetched-once reference/model assets in this
# backend (see backend/knowledge_base/models/) — regenerated automatically
# on first use on a fresh checkout, never committed.
_CACHE_FILE = Path(__file__).resolve().parent / 'hs_reference_cache.json'
_REFRESH_INTERVAL_SECONDS = 7 * 24 * 60 * 60

_reference: dict[str, str] | None = None
_loaded_at: float = 0.0


def _clean(text: str, code: str) -> str:
    # Comtrade's own text is "0902 - Tea" / "060311 - Flowers, cut; roses,
    # ..." — strip the leading "<code> - " so it reads as a plain name.
    prefix = f'{code} - '
    return text[len(prefix):] if text.startswith(prefix) else text


def _fetch() -> dict[str, str] | None:
    try:
        response = httpx.get(REFERENCE_URL, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        rows = response.json().get('results', [])
        return {row['id']: _clean(row['text'], row['id']) for row in rows if row.get('id') and row['id'] != 'TOTAL'}
    except Exception:
        return None


def _load_reference() -> dict[str, str]:
    """{HS code -> name} for every code (2/4/6-digit) in Comtrade's combined
    classification reference. Refetches at most once per process per week;
    a failed fetch never raises — callers fall back to a plain "HS <code>"
    label instead of a real name."""
    global _reference, _loaded_at
    if _reference is not None and time.time() - _loaded_at < _REFRESH_INTERVAL_SECONDS:
        return _reference

    if _reference is None and _CACHE_FILE.exists():
        cache_age = time.time() - _CACHE_FILE.stat().st_mtime
        try:
            _reference = json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
            _loaded_at = time.time() - max(0, cache_age - _REFRESH_INTERVAL_SECONDS)  # preserve "due for refresh" if already stale
        except (json.JSONDecodeError, OSError):
            _reference = None

    is_due = _reference is None or (time.time() - _loaded_at >= _REFRESH_INTERVAL_SECONDS)
    if is_due:
        fetched = _fetch()
        if fetched:
            _reference = fetched
            _loaded_at = time.time()
            try:
                _CACHE_FILE.write_text(json.dumps(_reference), encoding='utf-8')
            except OSError:
                pass
        elif _reference is None:
            _reference = {}
            _loaded_at = time.time()
        # else: refresh failed but an existing (stale) cache is still good enough to keep serving

    return _reference


def hs_name(code: str) -> str:
    """Official name for any HS code — 2-digit chapter, 4-digit heading, or
    6-digit subheading — from Comtrade's own combined classification
    reference. Falls back to a generic "HS <code>" label if the reference
    couldn't be loaded (no network, ever) and doesn't have that code."""
    code = str(code)
    return _load_reference().get(code) or f'HS {code}'


# Thin, purpose-named aliases so call sites read clearly (a category, a
# product, a subheading) even though all three share one lookup.
def chapter_name(hs2: str) -> str:
    return hs_name(str(hs2).zfill(2))


def product_description(hs4: str) -> str:
    return hs_name(hs4)


def subheading_description(hs6: str) -> str:
    return hs_name(hs6)


def list_searchable_hs_codes() -> list[dict]:
    """Every 4-digit (heading) and 6-digit (subheading) HS code, as
    [{hs_code, level, chapter, heading, description}] — the catalog the
    frontend's product search matches against. `level` (4 or 6) tells the
    frontend which drill-down view to open; `chapter`/`heading` are the
    codes to open it at. 2-digit chapters are left out — search is for
    finding a specific product, not a whole chapter. Never touches
    Comtrade's authenticated, quota-limited data API — only the free
    reference file already cached on disk."""
    entries = []
    for code, description in _load_reference().items():
        if not code.isdigit():
            continue
        if len(code) == 4:
            entries.append({'hs_code': code, 'level': 4, 'chapter': code[:2], 'heading': None, 'description': description})
        elif len(code) == 6:
            entries.append({'hs_code': code, 'level': 6, 'chapter': code[:2], 'heading': code[:4], 'description': description})
    return entries
