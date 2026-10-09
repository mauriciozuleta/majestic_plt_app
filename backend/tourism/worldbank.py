"""World Bank Indicators API connector (https://api.worldbank.org/v2/, no key). Documentation: datahelpdesk.worldbank.org/knowledgebase/articles/889392

Requests are by ISO alpha-3 code (several at once, separated by ';'), annual data, paginated. A country the World Bank does not list is never requested.
"""

from . import http
from .constants import INDICATORS, WORLD_BANK_INDICATORS

BASE_URL = 'https://api.worldbank.org/v2'
SOURCE_DATASET = 'World Development Indicators'
BATCH = 25  # countries per request


def indicator_url(country_iso3: str, indicator_id: str) -> str:
    return f'https://data.worldbank.org/indicator/{indicator_id}?locations={country_iso3[:2]}'


def fetch_indicator(iso3_codes: list[str], indicator_id: str, *, date_from: int = 1990, date_to: int | None = None) -> tuple[list[dict], str | None]:
    """All annual observations of one indicator for the given alpha-3 codes. Returns (rows, dataset edition = the API's 'lastupdated').
    A row is {iso3, iso2, year, value_text, obs_status}; null values are dropped. Raises http.ProviderError on API errors."""
    if not iso3_codes:
        return [], None
    from datetime import datetime, timezone

    date_to = date_to or datetime.now(timezone.utc).year
    url = f'{BASE_URL}/country/{";".join(iso3_codes)}/indicator/{indicator_id}'
    rows: list[dict] = []
    edition = None
    page = 1
    while True:
        data = http.get_json(url, {'format': 'json', 'per_page': 1000, 'page': page, 'date': f'{date_from}:{date_to}'})
        if not isinstance(data, list) or not data:
            raise http.ProviderError('Unexpected World Bank answer.')
        if isinstance(data[0], dict) and 'message' in data[0] and len(data) == 1:
            message = '; '.join(str(item.get('value') or item.get('key')) for item in data[0]['message'])
            raise http.ProviderError(f'World Bank API error: {message}')
        meta, items = data[0], data[1] if len(data) > 1 else None
        edition = meta.get('lastupdated') or edition
        for item in items or []:
            if item.get('value') is None:
                continue
            try:
                year = int(item['date'])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({
                'iso3': (item.get('countryiso3code') or '').upper(),
                'iso2': ((item.get('country') or {}).get('id') or '').upper(),
                'year': year,
                'value_text': repr(item['value']) if isinstance(item['value'], float) else str(item['value']),
                'obs_status': item.get('obs_status') or '',
            })
        if page >= int(meta.get('pages', 1)):
            break
        page += 1
    return rows, edition


def fetch_all(iso3_codes: list[str]) -> dict[str, tuple[list[dict], str | None]]:
    """{module indicator code: (rows, edition)} for receipts, GDP and population, in batches of BATCH countries."""
    out: dict[str, tuple[list[dict], str | None]] = {}
    for indicator_code, indicator_id in WORLD_BANK_INDICATORS.items():
        rows: list[dict] = []
        edition = None
        for start in range(0, len(iso3_codes), BATCH):
            batch_rows, edition = fetch_indicator(iso3_codes[start:start + BATCH], indicator_id)
            rows.extend(batch_rows)
        out[indicator_code] = (rows, edition)
    return out


def unit_of(indicator_code: str) -> str:
    return INDICATORS[indicator_code].unit
