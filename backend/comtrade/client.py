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


# Comtrade's response is broken down by mode of transport (motCode) and by
# a secondary "partner2" dimension on top of the partner/reporter/flow
# breakdown already asked for — leaving them unset returns every
# combination of both as separate rows (confirmed against live data: HS
# 0603 came back as 8 rows for one country/year/flow, one per motCode ×
# partner2Code combination, several of them exact duplicates of each other).
# motCode=0 is Comtrade's own "all modes of transport" total, and
# partner2Code=0 its "no partner2 breakdown" total — asking for exactly
# those, rather than requesting everything and filtering afterward, is both
# correct (no ambiguity about which duplicate to keep) and cheaper (the
# unfiltered call above returned 8x the rows this one does). Merged in here
# rather than left to each caller so no future query type can reintroduce
# the duplicate-rows bug by forgetting to ask for it.
_TOTALS_ONLY = {'motCode': 0, 'partner2Code': 0}


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

    rows = _call({'reporterCode': reporter_code, 'period': year, 'partnerCode': 0, 'cmdCode': 'AG6', 'flowCode': flow})
    # Same shape as fetch_products above: one call returns every 6-digit
    # subheading for the country/year, filtered here to the requested
    # heading.
    results = [
        {'hs_code': row['cmdCode'], 'description': classification.subheading_description(row['cmdCode']), 'value': _value_of(row)}
        for row in rows
        if row.get('cmdCode') and str(row['cmdCode'])[:4] == heading
    ]
    results.sort(key=lambda item: item['value'], reverse=True)
    snapshot_store.save_snapshot(db, cache_key, results)
    return results
