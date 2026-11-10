"""U.S. Energy Information Administration, API v2 (https://www.eia.gov/opendata/) — the primary automated source.

Every series ID below was CONFIRMED on 2026-11-09 by listing the route facets and pulling rows from https://api.eia.gov/v2/ (not taken from memory):
  petroleum/pri/spt   EER_EPJK_PF4_RGC_DPG  U.S. Gulf Coast kerosene-type jet fuel spot price FOB, $/gal   daily 1990-04-02 / weekly / monthly
                      RBRTE                 Europe Brent spot price FOB, $/bbl                               daily 1987-05-20 / weekly / monthly
  petroleum/stoc/wstk WKJSTUS1 / WDISTUS1   U.S. ending stocks of kerosene-type jet fuel / distillate fuel oil, MBBL      weekly since 1982-08-20
  petroleum/pnp/wiup  WPULEUS3              U.S. percent utilization of refinery operable capacity, %                      weekly since 1990-11-02
  petroleum/pnp/wprodrb WKJRPUS2            U.S. refiner and blender net production of kerosene-type jet fuel, MBBL/D      weekly since 1982-08-20
  petroleum/move/wkly WKJEXUS2              U.S. exports of kerosene-type jet fuel, MBBL/D                                  weekly since 2010-06-04

Terms (https://www.eia.gov/opendata/terms-of-service.php, read 2026-11-09): you may build a service that searches, displays, analyzes, retrieves EIA data; use the name "EIA" /
"U.S. Energy Information Administration" as the source and do not imply endorsement; the EIA logo needs written permission; do not modify content and still claim it is EIA's;
EIA may limit calls and block use that tries to exceed or circumvent limits (no numeric limit is published there). Data are US-government public domain
(https://www.eia.gov/about/copyrights_reuse.php, which asks for an acknowledgment such as "Source: U.S. Energy Information Administration").

The API key comes only from the EIA_API_KEY environment variable. It is sent as the api_key query parameter (the only way the v2 API takes it), so every error is rebuilt
without the URL and the key is scrubbed from any text that could reach a log or the UI.
"""

import os
import time
from datetime import date, timedelta

import httpx

from .. import units
from .base import Job, Observation, SourceAdapter

SOURCE_ID = 'eia_api'
BASE = 'https://api.eia.gov/v2/'
PAGE = 5000  # the API returns at most 5000 rows per request
PAUSE_SECONDS = 0.6  # politeness between requests; no numeric rate limit is published

SPT = 'petroleum/pri/spt'
JET_ID, BRENT_ID = 'EER_EPJK_PF4_RGC_DPG', 'RBRTE'

# job key -> dict(route, series, frequency (EIA name), schedule, kind, ...)
SERIES = {
    'jet_daily': dict(route=SPT, series=JET_ID, freq='daily', schedule='daily', kind='price', period='day'),
    'jet_weekly': dict(route=SPT, series=JET_ID, freq='weekly', schedule='weekly', kind='price', period='week'),
    'jet_monthly': dict(route=SPT, series=JET_ID, freq='monthly', schedule='monthly', kind='price', period='month'),
    'brent_daily': dict(route=SPT, series=BRENT_ID, freq='daily', schedule='daily', kind='driver', driver='brent', period='day'),
    'brent_weekly': dict(route=SPT, series=BRENT_ID, freq='weekly', schedule='weekly', kind='driver', driver='brent', period='week'),
    'brent_monthly': dict(route=SPT, series=BRENT_ID, freq='monthly', schedule='monthly', kind='driver', driver='brent', period='month'),
    'jet_stocks': dict(route='petroleum/stoc/wstk', series='WKJSTUS1', freq='weekly', schedule='weekly', kind='native', driver='jet_stocks', period='week'),
    'distillate_stocks': dict(route='petroleum/stoc/wstk', series='WDISTUS1', freq='weekly', schedule='weekly', kind='native', driver='distillate_stocks', period='week'),
    'refinery_util': dict(route='petroleum/pnp/wiup', series='WPULEUS3', freq='weekly', schedule='weekly', kind='native', driver='refinery_util', period='week'),
    'jet_production': dict(route='petroleum/pnp/wprodrb', series='WKJRPUS2', freq='weekly', schedule='weekly', kind='native', driver='jet_production', period='week'),
    'jet_exports': dict(route='petroleum/move/wkly', series='WKJEXUS2', freq='weekly', schedule='weekly', kind='native', driver='jet_exports', period='week'),
}
NATIVE_UNITS = {'MBBL': 'mbbl', 'MBBL/D': 'mbbl_d', '%': 'percent'}
OVERLAP = {'daily': timedelta(days=14), 'weekly': timedelta(days=35), 'monthly': timedelta(days=100)}


class EiaError(Exception):
    """Sanitised failure: never carries the request URL or the key."""


def _key() -> str:
    key = os.environ.get('EIA_API_KEY', '').strip()
    if not key:
        raise EiaError('EIA_API_KEY is not set in the environment (.env)')
    return key


def scrub(text: str) -> str:
    key = os.environ.get('EIA_API_KEY', '').strip()
    return text.replace(key, '<redacted>') if key else text


def _request(route: str, params: dict, tries: int = 4) -> dict:
    key = _key()
    delay = 2.0
    last = 'unknown error'
    for attempt in range(tries):
        try:
            response = httpx.get(f'{BASE}{route}', params={**params, 'api_key': key}, timeout=60, headers={'User-Agent': 'majestic-fuel-tracker/1.0'})
            if response.status_code in (429, 500, 502, 503, 504):
                last = f'HTTP {response.status_code}'
                wait = float(response.headers.get('Retry-After', delay)) if response.headers.get('Retry-After', '').isdigit() else delay
                time.sleep(min(wait, 60))
                delay *= 2
                continue
            if response.status_code in (401, 403):
                raise EiaError(f'HTTP {response.status_code}: the EIA API key was rejected')
            response.raise_for_status()
            body = response.json()
            if 'response' not in body:
                raise EiaError(scrub(str(body)[:200]))
            return body['response']
        except httpx.HTTPStatusError as exc:
            raise EiaError(f'HTTP {exc.response.status_code} from {route}') from None
        except httpx.HTTPError as exc:
            last = type(exc).__name__
            time.sleep(delay)
            delay *= 2
    raise EiaError(f'{route} failed after {tries} tries ({last})')


def _period_date(text: str) -> date:
    parts = [int(p) for p in text.split('-')]
    return date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)


def fetch_rows(route: str, series: str, freq: str, start: date | None = None) -> list[dict]:
    """All rows of one series, oldest first, paged by offset (5000 rows per page)."""
    rows: list[dict] = []
    offset = 0
    while True:
        params = {'frequency': freq, 'data[0]': 'value', 'facets[series][]': series, 'sort[0][column]': 'period', 'sort[0][direction]': 'asc', 'offset': offset, 'length': PAGE}
        if start:
            params['start'] = start.strftime('%Y-%m') if freq == 'monthly' else start.isoformat()
        response = _request(f'{route}/data', params)
        page = response.get('data', [])
        rows.extend(page)
        total = int(response.get('total', 0))
        offset += PAGE
        if not page or offset >= total:
            return rows
        time.sleep(PAUSE_SECONDS)


def parse_rows(job_key: str, rows: list[dict]) -> list[Observation]:
    spec = SERIES[job_key]
    out: list[Observation] = []
    for row in rows:
        raw = row.get('value')
        if raw in (None, '', '.'):
            continue
        value = float(raw)
        when = _period_date(row['period'])
        unit = row.get('units') or ''
        ref = {'eia_series': spec['series'], 'route': spec['route'], 'eia_units': unit, 'frequency': spec['freq']}
        series_id = f'{SOURCE_ID}:{spec["series"]}:{spec["freq"]}'
        if spec['kind'] == 'price':
            out.append(Observation(series_id=series_id, obs_date=when, value_usd_per_gal=units.to_usd_per_gal(value, 'usd_gal'), value_original=value, unit_original='usd_gal',
                                   currency_original='USD', period_type=spec['period'], geo_level='country', country_iso2='US', operator_class='scheduled', price_basis='spot',
                                   source_id=SOURCE_ID, raw_ref=ref))
        elif spec['kind'] == 'driver':
            out.append(Observation(series_id=series_id, obs_date=when, value_usd_per_gal=units.to_usd_per_gal(value, 'usd_bbl'), value_original=value, unit_original='usd_bbl',
                                   currency_original='USD', period_type=spec['period'], geo_level='global', price_basis='spot', source_id=SOURCE_ID, series_kind='driver',
                                   driver_code=spec['driver'], raw_ref=ref))
        else:
            native = NATIVE_UNITS.get(unit)
            if native is None:
                raise EiaError(f'unexpected unit {unit!r} for {spec["series"]}')
            out.append(Observation(series_id=series_id, obs_date=when, value_usd_per_gal=None, value_native=value, native_unit=native, unit_original=unit,
                                   period_type=spec['period'], geo_level='country', country_iso2='US', price_basis='index', source_id=SOURCE_ID, series_kind='driver',
                                   driver_code=spec['driver'], raw_ref=ref))
    return out


class EiaApiAdapter(SourceAdapter):
    source_id = SOURCE_ID
    automatic = True

    def jobs(self) -> list[Job]:
        return [Job(key, spec['schedule'], f'{spec.get("driver", "jet price")} ({spec["freq"]})', f'{SOURCE_ID}:{spec["series"]}:{spec["freq"]}') for key, spec in SERIES.items()]

    def fetch_job(self, key: str, since: date | None = None) -> list[Observation]:
        spec = SERIES[key]
        start = since - OVERLAP[spec['schedule']] if since else None
        return parse_rows(key, fetch_rows(spec['route'], spec['series'], spec['freq'], start))

    def fetch(self, since: date | None = None) -> list[Observation]:
        out: list[Observation] = []
        for key in SERIES:
            out.extend(self.fetch_job(key, since))
            time.sleep(PAUSE_SECONDS)
        return out
