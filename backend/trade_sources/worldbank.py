"""World Bank Indicators API client — population and GDP-per-capita, the two
regression predictors SAM Overview's opt-in estimation layer fits against
(see backend/estimation/regression.py and MARKET_SIZING_METHODOLOGY.md). Free and
keyless. Confirmed against the live API: it takes ISO alpha-2 country codes
(e.g. `.../country/US/indicator/...` — no ISO3 translation needed), matching
this app's own CountryReferenceCatalog.country_code exactly, and
`mrnev=1` ("most recent non-empty value") returns exactly one row per
country holding whichever year that indicator was last actually reported
for — which is resolved INDEPENDENTLY per indicator (a country's population
figure and its GDP-per-capita figure can legitimately come from different
years), so population and GDP-per-capita are always fetched as two separate
calls, never assumed to share a year.

Several countries can be requested in one call (semicolon-joined codes,
e.g. `.../country/US;PH;CO/indicator/...`) — confirmed live. Each
(indicator, country) result is cached indefinitely via snapshot_store, the
same "a published figure doesn't change" reasoning backend/comtrade/
client.py already uses for Comtrade: a batch call only ever asks the World
Bank for the countries not already cached. A country the World Bank has no
data for (or doesn't recognize) is simply absent from the result — never
zero — and that absence is cached too, so it isn't re-requested on every
call; a genuinely failed request (network/HTTP error) is NOT cached, so a
transient outage doesn't get baked in as "no data" (mirrors comtrade/
client.py's own only-cache-successes rule)."""

import httpx
from sqlalchemy.orm import Session

from .. import snapshot_store

BASE_URL = 'https://api.worldbank.org/v2/country'
TIMEOUT = 30
# Keeps each request's URL and response modest; well within the World
# Bank's own per-call limits (which are far higher than this app will ever
# need — its whole portfolio is a handful of countries per region).
BATCH_SIZE = 50

POPULATION_INDICATOR = 'SP.POP.TOTL'
GDP_PER_CAPITA_INDICATOR = 'NY.GDP.PCAP.CD'


class WorldBankError(Exception):
    """A user-presentable reason a World Bank call failed."""


def _cache_key(indicator: str, iso2: str) -> str:
    return f'worldbank_{indicator}_{iso2.upper()}'


def _fetch_indicator_batch(iso2_codes: list[str], indicator: str) -> dict[str, dict]:
    """{iso2: {'value': float, 'year': int}} for every code the World Bank
    actually returned a most-recent-non-empty value for. Raises
    WorldBankError on a real network/HTTP failure — a code the World Bank
    doesn't recognize, or has no data for this indicator, is just absent
    from the returned dict (not an error), matching fetch_categories' own
    missing-vs-zero rule elsewhere in this codebase."""
    if not iso2_codes:
        return {}
    codes = ';'.join(iso2_codes)
    url = f'{BASE_URL}/{codes}/indicator/{indicator}'
    try:
        response = httpx.get(url, params={'format': 'json', 'mrnev': 1, 'per_page': 300}, timeout=TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise WorldBankError(f'Could not reach the World Bank API: {error}') from error
    try:
        payload = response.json()
    except ValueError as error:
        raise WorldBankError('World Bank API returned something unreadable.') from error
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        # The World Bank's own error shape is a single-element list with a
        # `message` object instead of the usual [meta, data] pair (seen live
        # for a malformed indicator/country code) — treated as "no data"
        # rather than raised, since it's not a transient failure worth
        # retrying, just nothing usable for the requested codes.
        return {}
    results = {}
    for row in payload[1]:
        value = row.get('value')
        iso2 = (row.get('country') or {}).get('id')
        year = row.get('date')
        if value is None or not iso2 or not year:
            continue
        results[iso2.upper()] = {'value': float(value), 'year': int(year)}
    return results


def fetch_population_and_gdp(db: Session, iso2_codes: list[str]) -> dict[str, dict]:
    """{iso2: {population, population_year, gdp_per_capita, gdp_per_capita_year}}
    for every requested country — a country the World Bank has no figure for
    (either indicator) simply has None in that field, never 0, so a caller
    can tell "confirmed zero" (impossible here) apart from "not available"
    (the normal case for a small territory). Population and GDP-per-capita
    are category-independent facts — call this ONCE per set of countries and
    reuse the result across every category's regression, never refetch it
    per category (see routers/comtrade.py's sam_overview_estimates)."""
    codes = sorted({c.upper() for c in iso2_codes if c})
    result = {
        c: {'population': None, 'population_year': None, 'gdp_per_capita': None, 'gdp_per_capita_year': None} for c in codes
    }

    for indicator, value_field, year_field in (
        (POPULATION_INDICATOR, 'population', 'population_year'),
        (GDP_PER_CAPITA_INDICATOR, 'gdp_per_capita', 'gdp_per_capita_year'),
    ):
        cache_key_by_code = {c: _cache_key(indicator, c) for c in codes}
        cached_rows = {row['source']: row['products'] for row in snapshot_store.list_snapshots(db, list(cache_key_by_code.values()))}
        to_fetch = [c for c in codes if cache_key_by_code[c] not in cached_rows]

        for batch_start in range(0, len(to_fetch), BATCH_SIZE):
            batch = to_fetch[batch_start : batch_start + BATCH_SIZE]
            try:
                fetched = _fetch_indicator_batch(batch, indicator)
            except WorldBankError:
                # Leave this batch uncached entirely so a transient outage
                # gets retried next time, rather than baked in as "no data"
                # for every country in it.
                continue
            for code in batch:
                row = fetched.get(code)
                snapshot_store.save_snapshot(db, cache_key_by_code[code], row)
                cached_rows[cache_key_by_code[code]] = row

        for code in codes:
            row = cached_rows.get(cache_key_by_code[code])
            if row:
                result[code][value_field] = row['value']
                result[code][year_field] = row['year']

    return result
