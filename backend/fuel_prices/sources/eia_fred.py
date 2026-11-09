"""US Gulf Coast kerosene-type jet fuel spot (EIA) and Brent spot (EIA), read through FRED's public CSV download (no API key needed; robots.txt of fred.stlouisfed.org
allows /graph/fredgraph.csv at a 1 s crawl delay). If FRED_API_KEY is set it is NOT used here — the CSV endpoint is enough, so no secret ever touches this code.

Series (verified to exist on 2026-11-09 by downloading them): DJFUELUSGULF (daily jet, USD/gal), MJFUELUSGULF (monthly), DCOILBRENTEU (daily Brent, USD/bbl).
"""

import csv
import io
import time
from datetime import date, datetime

import httpx

from .. import units
from .base import Observation, SourceAdapter

SOURCE_ID = 'eia_fred'
FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv'
HEADERS = {'User-Agent': 'majestic-fuel-tracker/1.0 (research)'}

# fred series id -> (period, unit, kind, driver code, price basis)
SERIES = {
    'DJFUELUSGULF': ('day', 'usd_gal', 'price', None, 'spot'),
    'MJFUELUSGULF': ('month', 'usd_gal', 'price', None, 'spot'),
    'DCOILBRENTEU': ('day', 'usd_bbl', 'driver', 'brent', 'spot'),
}


def parse_csv(text: str, fred_id: str) -> list[Observation]:
    period, unit, kind, driver, basis = SERIES[fred_id]
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = (row.get(fred_id) or '').strip()
        if not raw or raw == '.':  # FRED marks missing days with '.'
            continue
        obs_date = date.fromisoformat(row['observation_date'])
        value = float(raw)
        is_jet = kind == 'price'
        out.append(Observation(
            series_id=f'{SOURCE_ID}:{fred_id}', obs_date=obs_date, value_usd_per_gal=units.to_usd_per_gal(value, unit),
            value_original=value, unit_original=unit, currency_original='USD', period_type=period,
            geo_level='country' if is_jet else 'global', country_iso2='US' if is_jet else None,
            operator_class='scheduled' if is_jet else 'unspecified',  # a wholesale spot benchmark is the scheduled-carrier type of price
            price_basis=basis, source_id=SOURCE_ID, series_kind=kind, driver_code=driver,
            raw_ref={'fred_series': fred_id, 'origin': 'EIA'}))
    return out


def _get(url: str, params: dict, tries: int = 3) -> str:
    delay = 2.0
    for attempt in range(tries):
        try:
            response = httpx.get(url, params=params, headers=HEADERS, timeout=60, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError('unreachable')


class EiaFredAdapter(SourceAdapter):
    source_id = SOURCE_ID
    automatic = True

    def fetch(self, since: date | None = None) -> list[Observation]:
        out: list[Observation] = []
        for fred_id in SERIES:
            params = {'id': fred_id}
            if since:
                params['cosd'] = since.isoformat()
            out.extend(parse_csv(_get(FRED_CSV, params), fred_id))
            time.sleep(1.0)  # FRED's robots.txt crawl delay
        return out
