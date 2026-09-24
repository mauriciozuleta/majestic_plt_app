"""Tier 3 of the fallback discovery chain — US Census bilateral goods-trade
series, as republished by FRED (Federal Reserve Economic Data). This is
the one tier built to be genuinely generic/scalable rather than a
per-territory special case: most small territories that report nothing to
UN Comtrade still show up as a named US bilateral trading partner in
Census's own series, and FRED republishes those under predictable
EXP<code>/IMP<code> series IDs, where <code> is the US Census Bureau's own
Schedule-C country code.

A small seed map below covers the two territories this feature was
researched against — verified live on fred.stlouisfed.org, not guessed:
  - EXP2430 / IMP2430 — U.S. exports/imports of goods, Turks and Caicos Islands
  - EXP2774 / IMP2774 — U.S. exports/imports of goods, Sint Maarten
Anything outside the seed map falls through to FRED's own series/search
API, matched against the same title convention Census uses for every
other bilateral series ("U.S. Exports of Goods ... to <country>") — best
effort, and deliberately conservative (an unmatched country_name returns
nothing rather than guessing).

Access/terms: FRED is a key-authenticated REST API
(https://fred.stlouisfed.org/docs/api/), not a scraped website — no
robots.txt applies to it (see trade_sources/robots.py's own docstring),
and its published terms only require a free, registered API key
(FRED_API_KEY, see .env.example), which this module reads and gracefully
no-ops without (see is_configured/probe below) — it never blocks
discovery or fabricates a key.

Direction mapping — easy to get backwards, so spelled out once, here: an
"EXP" series is *U.S. exports TO* the territory — i.e., from the
territory's own point of view, that's its IMPORTS (flow 'M'). An "IMP"
series is *U.S. imports FROM* the territory — the territory's own EXPORTS
(flow 'X').

Coverage limitation, also spelled out once: this tier can only ever offer
a single aggregate dollar figure per year/flow — Census's own bilateral
series are not broken out by HS product, so there is no category/product/
subheading drill-down to build from them, unlike Comtrade. Coverage is
therefore always stored as 'bilateral' (US trade only, not the
territory's total trade with the world) with a note explaining both
limitations — see discovery.py's REGISTRY of stored notes.
"""

import os

import httpx

from .. import snapshot_store

BASE_URL = 'https://api.stlouisfed.org/fred'
TIMEOUT = 20
_PROBE_YEARS_BACK = 4

# Census Bureau Schedule-C country codes for territories actually
# researched for this feature (see module docstring for how these were
# verified). Extend as more territories are researched — anything absent
# falls through to the generic name search in _find_series_ids below.
_SEED_CENSUS_CODES = {
    'TC': '2430',
    'SX': '2774',
}


def _api_key() -> str | None:
    return os.environ.get('FRED_API_KEY')


def is_configured() -> bool:
    return bool(_api_key())


def _get(path: str, params: dict) -> dict:
    request_params = {**params, 'api_key': _api_key(), 'file_type': 'json'}
    response = httpx.get(f'{BASE_URL}/{path}', params=request_params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def find_series_ids(country_code: str, country_name: str) -> tuple[str, str] | None:
    """(export_series_id, import_series_id) — both named from the US's own
    point of view, see module docstring — or None if no matching pair
    could be found/confirmed for this territory."""
    code = _SEED_CENSUS_CODES.get((country_code or '').upper())
    if code:
        return f'EXP{code}', f'IMP{code}'

    if not is_configured():
        return None
    try:
        data = _get('series/search', {'search_text': f'U.S. Exports of Goods {country_name}', 'limit': 20})
    except (httpx.HTTPError, ValueError):
        return None

    export_id = None
    needle = (country_name or '').lower()
    for row in data.get('seriess', []):
        title = (row.get('title') or '').lower()
        series_id = row.get('id') or ''
        # Deliberately conservative: only accept a series whose id has the
        # expected Census "EXP" prefix AND whose own title names both
        # "exports of goods" and this exact territory — a loose text match
        # here could silently attach the wrong country's figures.
        if series_id.startswith('EXP') and needle in title and 'exports of goods' in title:
            export_id = series_id
            break
    if not export_id:
        return None
    return export_id, 'IMP' + export_id[len('EXP') :]


def _annual_total(series_id: str, year: int) -> float | None:
    """Sums FRED's monthly observations for `series_id` within `year` into
    an annual total, in actual dollars (FRED reports these series in
    millions). None if the series has no usable observations for that
    year — not yet reported, or the series doesn't exist."""
    try:
        data = _get(
            'series/observations',
            {'series_id': series_id, 'observation_start': f'{year}-01-01', 'observation_end': f'{year}-12-31'},
        )
    except (httpx.HTTPError, ValueError):
        return None

    total = 0.0
    found = False
    for row in data.get('observations', []):
        value = row.get('value')
        if value in (None, '.'):
            continue
        try:
            total += float(value) * 1_000_000
            found = True
        except ValueError:
            continue
    return total if found else None


def probe(country_code: str, country_name: str, year: int) -> dict | None:
    """Discovery-time check: does this territory have any usable FRED/
    Census bilateral data at all? Walks back a few years the same way the
    Comtrade quick-check does (a small territory can lag). Returns
    {'export_series', 'import_series'} once at least one non-empty
    year is confirmed, else None (not configured, no matching series, or
    genuinely nothing reported)."""
    if not is_configured():
        return None
    series = find_series_ids(country_code, country_name)
    if not series:
        return None
    export_series, import_series = series
    for offset in range(_PROBE_YEARS_BACK):
        probe_year = year - offset
        if _annual_total(export_series, probe_year) is not None or _annual_total(import_series, probe_year) is not None:
            return {'export_series': export_series, 'import_series': import_series}
    return None


def fetch_total(db, country_code: str, export_series: str, import_series: str, year: int, flow: str) -> float | None:
    """The one figure this tier can offer: total US-bilateral goods trade
    for one flow/year, in actual dollars — flow='M' (the territory's
    imports) reads the EXP series, flow='X' (its exports) reads the IMP
    series (see module docstring). Cached indefinitely once found, same
    "never cache a failure, only a real result" convention as
    comtrade/client.py."""
    series_id = export_series if flow == 'M' else import_series
    cache_key = f'fred_bilateral_{flow}_{country_code}_{year}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        rows = cached[0]['products']
        return rows[0]['value'] if rows else None

    value = _annual_total(series_id, year)
    if value is not None:
        snapshot_store.save_snapshot(db, cache_key, [{'value': value}])
    return value
