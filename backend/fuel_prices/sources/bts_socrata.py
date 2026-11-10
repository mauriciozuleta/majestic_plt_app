"""BTS Form 41 Schedule P-12(a) as published on data.bts.gov (Socrata), ANNUAL only.

Datasets, verified 2026-11-09 against https://data.bts.gov/api/views/<id>.json and /resource/<id>.json (37 rows each, 1990 -> latest year):
  navd-gpqa  AFF - P12a - Fuel Cost by Carrier Group          columns year, total, large_regional_carriers, national_carriers, major_carriers   (USD)
  33xp-y9fx  AFF - P12a - Fuel Consumption by Carrier Group   same columns                                                                       (gallons)
Both carry license "Public Domain U.S. Government" (https://www.usa.gov/government-works) and attribution "U.S. DOT/Bureau of Transportation Statistics".
Price = cost / gallons per year and carrier group (derived, quality 'derived', basis airline_paid). Limits, stated plainly:
  * annual, not monthly (the monthly P-12(a) table exists only on TranStats; see the drop folder), and a part-year row such as "2026M1-6" is skipped;
  * the datasets do not say whether non-scheduled service is included, so operator_class is 'unspecified' (the TranStats fuel table is titled "Scheduled" — not confirmed for these).
data.bts.gov robots.txt asks for a 1 s crawl delay; no key is needed (Socrata app tokens are optional and not used).
"""

import re
import time
from datetime import date

import httpx

from .base import Job, Observation, SourceAdapter

SOURCE_ID = 'bts_socrata'
BASE = 'https://data.bts.gov/resource/'
COST_ID, GALLONS_ID = 'navd-gpqa', '33xp-y9fx'
GROUPS = {'total': 'total', 'large_regional_carriers': 'large_regional', 'national_carriers': 'national', 'major_carriers': 'major'}  # explicit column map


class BtsSocrataError(Exception):
    pass


def _get(dataset: str, tries: int = 3) -> list[dict]:
    delay = 2.0
    for attempt in range(tries):
        try:
            response = httpx.get(f'{BASE}{dataset}.json', params={'$limit': 1000}, timeout=60, headers={'User-Agent': 'majestic-fuel-tracker/1.0'})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            if attempt == tries - 1:
                raise BtsSocrataError(f'{dataset}: {type(exc).__name__}') from None
            time.sleep(delay)
            delay *= 2
    return []


def parse(cost_rows: list[dict], gallon_rows: list[dict]) -> list[Observation]:
    gallons = {r['year']: r for r in gallon_rows}
    out = []
    for row in cost_rows:
        year = row.get('year', '')
        if not re.fullmatch(r'\d{4}', year) or year not in gallons:
            continue  # part-year rows ("2026M1-6") and years missing on either side
        for column, group in GROUPS.items():
            try:
                cost, gal = float(row[column]), float(gallons[year][column])
            except (KeyError, ValueError):
                continue
            if cost <= 0 or gal <= 0:
                continue
            price = cost / gal
            out.append(Observation(
                series_id=f'{SOURCE_ID}:US:{group}', obs_date=date(int(year), 1, 1), value_usd_per_gal=price, value_original=price, unit_original='usd_gal', currency_original='USD',
                period_type='year', geo_level='country', country_iso2='US', operator_class='unspecified', price_basis='airline_paid', source_id=SOURCE_ID, quality='derived',
                raw_ref={'cost_dataset': COST_ID, 'gallons_dataset': GALLONS_ID, 'column': column, 'cost_usd': cost, 'gallons': gal, 'carrier_group': group,
                         'formula': 'cost / gallons'}))
    return out


class BtsSocrataAdapter(SourceAdapter):
    source_id = SOURCE_ID
    automatic = True

    def jobs(self) -> list[Job]:
        return [Job('annual', 'weekly', 'P-12(a) annual fuel cost / gallons')]  # the datasets are tiny; weekly polling picks up the next annual update

    def fetch(self, since: date | None = None) -> list[Observation]:
        cost = _get(COST_ID)
        time.sleep(1.0)
        return parse(cost, _get(GALLONS_ID))
