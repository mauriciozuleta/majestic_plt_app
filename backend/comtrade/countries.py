"""Countries the Global Trade Data module can pull UN Comtrade figures for.

A country here needs a Comtrade *reporterCode* — the numeric code Comtrade
itself assigns to the country that files the trade statistics. This is NOT
the same code space this app uses elsewhere for other data sources —
Jamaica's FAOSTAT area code is 109, but its Comtrade reporterCode is 388;
using one system's code with another's API returns either an error or,
worse, silently wrong data (Comtrade reporter 280 is not Sint Maarten, it's
the pre-1990 Federal Republic of Germany). So every entry here comes
straight from Comtrade's own public reference file
(comtradeapi.un.org/files/v1/app/reference/Reporters.json) — never a code
looked up or guessed from another system — same "fetch once, cache to
disk, refresh weekly, fall back to the existing cache on a failed refresh"
recipe as comtrade/classification.py's HS reference.

Filtered to real, currently-reporting countries: `isGroup` entries are
Comtrade aggregates ("World", "EU", ...), not real reporters, and an entry
with an `entryExpiredDate` is a defunct/historical reporter (e.g. "Arab
Rep. of Yemen (...1990)") that would only ever return old, superseded data
under a name a user never typed.

`iso2` (reporterCodeIsoAlpha2) is what lets the Global Trade Data page
group these by the same geographic region Commercial Structure uses
(CountryReferenceCatalog.country_code is also ISO alpha-2) — see
routers/comtrade.py's list_trade_countries. It's an independent,
Comtrade-published field, not a guess bridging the two code spaces either.
"""

import json
import time
from pathlib import Path

import httpx

REFERENCE_URL = 'https://comtradeapi.un.org/files/v1/app/reference/Reporters.json'
_CACHE_FILE = Path(__file__).resolve().parent / 'reporters_cache.json'
_REFRESH_INTERVAL_SECONDS = 7 * 24 * 60 * 60

_countries: list[dict] | None = None
_loaded_at: float = 0.0


def _fetch() -> list[dict] | None:
    try:
        response = httpx.get(REFERENCE_URL, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        rows = response.json().get('results', [])
        return [
            {
                'name': row['text'],
                'reporter_code': row['reporterCode'],
                'iso2': row.get('reporterCodeIsoAlpha2') or None,
                'iso3': row.get('reporterCodeIsoAlpha3') or None,
            }
            for row in rows
            if not row.get('isGroup') and not row.get('entryExpiredDate') and row.get('reporterCode')
        ]
    except Exception:
        return None


def list_tracked_countries() -> list[dict]:
    """{name, reporter_code, iso2, iso3} for every country Comtrade currently
    accepts a reporterCode for. Refetches at most once per process per week;
    a failed fetch falls back to the existing cache (or, on a fresh
    checkout with no cache and no network yet, an empty list — the frontend
    already handles that as a load error, same as any other fetch failure)."""
    global _countries, _loaded_at
    if _countries is not None and time.time() - _loaded_at < _REFRESH_INTERVAL_SECONDS:
        return _countries

    if _countries is None and _CACHE_FILE.exists():
        cache_age = time.time() - _CACHE_FILE.stat().st_mtime
        try:
            _countries = json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
            _loaded_at = time.time() - max(0, cache_age - _REFRESH_INTERVAL_SECONDS)
        except (json.JSONDecodeError, OSError):
            _countries = None

    is_due = _countries is None or (time.time() - _loaded_at >= _REFRESH_INTERVAL_SECONDS)
    if is_due:
        fetched = _fetch()
        if fetched:
            _countries = fetched
            _loaded_at = time.time()
            try:
                _CACHE_FILE.write_text(json.dumps(_countries), encoding='utf-8')
            except OSError:
                pass

    if _countries is None:
        _countries = []
    return _countries
