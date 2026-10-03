"""Server-side UN Comtrade client — the only place the subscription key
touches the network. It's read from COMTRADE_API_KEY (see backend/main.py's
load_dotenv() / the project's .env), never sent to or read from the
browser: the frontend only ever talks to routers/comtrade.py, which calls
these functions and forwards their result.

Annual trade figures for an already-published year don't change once
Comtrade has them, so a successful (country, year, chapter, flow) result is
cached indefinitely, via the same snapshot mechanism the price-comparison
modules already use (snapshot_store.py) — keeps repeat views fast and
protects the free tier's 500-calls/day limit. A failed call is never
cached, so a bad key or a transient outage doesn't get baked in as
"no data" — only a real, successful empty result does, and that's cached
too (that's exactly what lets a small territory with nothing reported stay
fast to re-view instead of re-hitting the API every time).
"""

import os

import httpx
from sqlalchemy.orm import Session

from .. import snapshot_store
from . import classification

BASE_URL = 'https://comtradeapi.un.org/data/v1/get/C/A/HS'
TIMEOUT = 40


class ComtradeError(Exception):
    """A user-presentable reason a Comtrade call failed."""


def _api_key() -> str | None:
    return os.environ.get('COMTRADE_API_KEY')


def _value_of(row: dict) -> float:
    # primaryValue is Comtrade's own recommended trade-value field (already
    # picks CIF for imports / FOB for exports); fall back to whichever of
    # those is actually present on the rare row that omits it.
    for field in ('primaryValue', 'cifvalue', 'fobvalue'):
        value = row.get(field)
        if value is not None:
            return float(value)
    return 0.0


# Comtrade's response is broken down by mode of transport (motCode), by a
# secondary "partner2" dimension, and by customs procedure (customsCode) on
# top of the partner/reporter/flow breakdown already asked for — leaving
# any of them unset returns every combination of all three as separate rows
# (confirmed against live data: HS 0603 came back as 8 rows for one
# country/year/flow, one per motCode × partner2Code combination; separately
# confirmed a global chapter-02 pull for 2023 came back with 37 of 166 real
# reporting countries duplicated 2-3x each, purely from unfiltered
# customsCode — e.g. reporter 100's chapter 27 had C00/C01/C20 rows worth
# 5.97B / 5.14B / 0.83B respectively, a >2x inflation risk if all three were
# summed as if additive). motCode=0 is Comtrade's own "all modes of
# transport" total, partner2Code=0 its "no partner2 breakdown" total, and
# customsCode='C00' its "TOTAL CPC" (all customs procedures combined) total
# — confirmed live that every one of a real query's reporters has a C00 row
# (i.e. requesting it loses no country, C00 isn't itself a partial
# procedure). Asking for exactly those three, rather than requesting
# everything and filtering afterward, is both correct (no ambiguity about
# which duplicate to keep) and cheaper (the fully unfiltered call for one
# chapter/year returned ~20x the rows this one does). Merged in here rather
# than left to each caller so no future query type can reintroduce the
# duplicate-rows bug by forgetting to ask for any of the three.
_TOTALS_ONLY = {'motCode': 0, 'partner2Code': 0, 'customsCode': 'C00'}


def _call(params: dict) -> list[dict]:
    api_key = _api_key()
    if not api_key:
        raise ComtradeError('No UN Comtrade API key is configured on the server (COMTRADE_API_KEY).')
    params = {**params, **_TOTALS_ONLY}
    try:
        response = httpx.get(BASE_URL, params=params, headers={'Ocp-Apim-Subscription-Key': api_key}, timeout=TIMEOUT)
    except httpx.HTTPError as error:
        raise ComtradeError(f'Could not reach UN Comtrade: {error}') from error

    if response.status_code == 401:
        raise ComtradeError('UN Comtrade rejected the configured API key.')
    if response.status_code == 429:
        raise ComtradeError("UN Comtrade's daily call limit has been reached — try again tomorrow.")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise ComtradeError(f'UN Comtrade returned an error ({response.status_code}).') from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ComtradeError('UN Comtrade returned something unreadable.') from error
    if payload.get('data') is None:
        # Comtrade reports some of its own errors (a malformed parameter,
        # for instance) inside an otherwise-200 response.
        raise ComtradeError(payload.get('error') or 'UN Comtrade returned no data.')
    return payload['data']


def fetch_categories(db: Session, reporter_code: int, year: int, flow: str) -> list[dict]:
    """[{hs_code, category_name, value}] of HS 2-digit chapter totals for
    one country/year/flow, sorted by value descending. Cached indefinitely
    once fetched — see module docstring."""
    cache_key = f'comtrade_categories_{flow}_{reporter_code}_{year}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        return cached[0]['products']

    rows = _call({'reporterCode': reporter_code, 'period': year, 'partnerCode': 0, 'cmdCode': 'AG2', 'flowCode': flow})
    results = [
        {'hs_code': row['cmdCode'], 'category_name': classification.chapter_name(row['cmdCode']), 'value': _value_of(row)}
        for row in rows
        if row.get('cmdCode')
    ]
    results.sort(key=lambda item: item['value'], reverse=True)
    snapshot_store.save_snapshot(db, cache_key, results)
    return results


def fetch_products(db: Session, reporter_code: int, year: int, flow: str, chapter: str) -> list[dict]:
    """[{hs_code, description, value}] of HS 4-digit product totals within
    one chapter, for one country/year/flow, sorted by value descending.
    Cached indefinitely once fetched — see module docstring."""
    chapter = str(chapter).zfill(2)
    cache_key = f'comtrade_products_{flow}_{reporter_code}_{year}_{chapter}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        return cached[0]['products']

    rows = _call({'reporterCode': reporter_code, 'period': year, 'partnerCode': 0, 'cmdCode': 'AG4', 'flowCode': flow})
    # This call returns every 4-digit product for the country/year in one
    # response (Comtrade has no per-chapter filter for it) — filtered here
    # to the requested chapter, as the endpoint contract promises.
    results = [
        {'hs_code': row['cmdCode'], 'description': classification.product_description(row['cmdCode']), 'value': _value_of(row)}
        for row in rows
        if row.get('cmdCode') and str(row['cmdCode'])[:2] == chapter
    ]
    results.sort(key=lambda item: item['value'], reverse=True)
    snapshot_store.save_snapshot(db, cache_key, results)
    return results


def fetch_subheadings(db: Session, reporter_code: int, year: int, flow: str, heading: str) -> list[dict]:
    """[{hs_code, description, value}] of HS 6-digit subheading totals
    within one 4-digit heading, for one country/year/flow, sorted by value
    descending. 6-digit is the deepest internationally standardized HS
    level — Comtrade doesn't publish comparable data beyond it (8+ digit
    codes are national extensions that differ per country), so this is the
    final drill-down level. Cached indefinitely once fetched — see module
    docstring."""
    heading = str(heading).zfill(4)
    cache_key = f'comtrade_subheadings_{flow}_{reporter_code}_{year}_{heading}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        return cached[0]['products']

    # One call returns every 6-digit subheading for the country/year (see
    # fetch_all_subheadings, which caches that whole set), filtered here to
    # the requested heading.
    results = [
        {'hs_code': code, 'description': classification.subheading_description(code), 'value': value}
        for code, value in fetch_all_subheadings(db, reporter_code, year, flow).items()
        if code[:4] == heading
    ]
    results.sort(key=lambda item: item['value'], reverse=True)
    snapshot_store.save_snapshot(db, cache_key, results)
    return results


def fetch_all_subheadings(db: Session, reporter_code: int, year: int, flow: str) -> dict[str, float]:
    """{hs6_code: value} for every 6-digit subheading one country reported
    for one year/flow — a single Comtrade call (AG6 has no per-heading
    filter, so this is what every subheading lookup costs anyway), cached
    indefinitely as a whole so any later lookup for that country/year, for
    any product, costs nothing (see product-level SAM in
    routers/comtrade.py)."""
    cache_key = f'comtrade_all_subheadings_{flow}_{reporter_code}_{year}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        return cached[0]['products']

    rows = _call({'reporterCode': reporter_code, 'period': year, 'partnerCode': 0, 'cmdCode': 'AG6', 'flowCode': flow})
    values = {str(row['cmdCode']): _value_of(row) for row in rows if row.get('cmdCode')}
    snapshot_store.save_snapshot(db, cache_key, values)
    return values


def fetch_global_total(db: Session, chapter: str, year: int, flow: str) -> list[dict]:
    """[{reporter_code, value}] — one row per UN Comtrade reporting country,
    worldwide, for one HS 2-digit chapter/year/flow (Global TAM's raw
    input). `reporterCode` is deliberately omitted from the request (not
    set to 0 — confirmed live that reporterCode=0 returns an empty result,
    there is no "World" reporter; see MARKET_SIZING_METHODOLOGY.md), which
    is what makes Comtrade return every reporter's own row instead of one
    country's. `partnerCode=0` here is a different axis entirely — it
    means "every partner combined" (so each reporter's row is its total
    trade with the world, not broken out by partner), not a "World
    reporter"; conflating the two was confirmed live to silently return
    nothing. Cached indefinitely once fetched, same convention as
    fetch_categories — a global pull is meaningfully larger (~150-250 rows)
    than a per-country one, so avoiding a re-fetch matters even more here
    for the free tier's daily call limit."""
    chapter = str(chapter).zfill(2)
    cache_key = f'comtrade_global_total_{flow}_{chapter}_{year}'
    cached = snapshot_store.list_snapshots(db, [cache_key])
    if cached:
        return cached[0]['products']

    rows = _call({'period': year, 'partnerCode': 0, 'cmdCode': chapter, 'flowCode': flow})
    results = [{'reporter_code': row['reporterCode'], 'value': _value_of(row)} for row in rows if row.get('reporterCode') is not None]
    snapshot_store.save_snapshot(db, cache_key, results)
    return results
