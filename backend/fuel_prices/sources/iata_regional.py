"""IATA Jet Fuel Price Monitor (IATA-Platts) — regional weekly indices, imported from a file until the licence is confirmed (terms_status stays 'unverified').

The expected file is a simple CSV you prepare from the monitor: obs_date, region (Global | North America | Latin America & Caribbean | Europe & CIS | Middle East | Africa |
Asia-Pacific), and one price column named usd_bbl, cts_gal or usd_mt. If both usd_bbl and usd_mt are present the implied barrels per metric ton is reported, to confirm the
configured BBL_PER_METRIC_TON. The price basis (spot vs into-plane) is NOT stated by IATA's sheet as far as I could verify, so it is recorded as 'index'.
"""

import csv
import io
from datetime import date

from .. import units
from .base import Observation

SOURCE_ID = 'iata_regional'
REGION_CODES = {'global': None, 'north america': 'NA', 'latin america & caribbean': 'LAC', 'latin america and caribbean': 'LAC', 'europe & cis': 'EUR', 'europe and cis': 'EUR',
                'middle east': 'ME', 'africa': 'AF', 'asia-pacific': 'APAC', 'asia pacific': 'APAC'}
PRICE_COLUMNS = ('usd_bbl', 'cts_gal', 'usd_mt')


def parse(text: str, source_id: str = SOURCE_ID) -> tuple[list[Observation], list[str], dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ['the file is empty'], {}
    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
    columns = [col for col in PRICE_COLUMNS if col in reader.fieldnames]
    if 'obs_date' not in reader.fieldnames or 'region' not in reader.fieldnames or not columns:
        return [], ['need columns obs_date, region and at least one of usd_bbl / cts_gal / usd_mt'], {}
    out, errors, implied = [], [], []
    for line, row in enumerate(reader, start=2):
        try:
            region = REGION_CODES[row['region'].strip().lower()]
            obs_date = date.fromisoformat(row['obs_date'].strip())
            col = columns[0]  # first listed price column is the stored one (bbl > cts_gal > mt)
            value = float(row[col])
            if 'usd_bbl' in columns and 'usd_mt' in columns and row.get('usd_mt'):
                implied.append(float(row['usd_mt']) / float(row['usd_bbl']))
            out.append(Observation(
                series_id=f'{source_id}:{region or "GLOBAL"}', obs_date=obs_date, value_usd_per_gal=units.to_usd_per_gal(value, col), value_original=value, unit_original=col,
                currency_original='USD', period_type='week', geo_level='region' if region else 'global', region_code=region, operator_class='scheduled', price_basis='index',
                source_id=source_id, quality='observed', raw_ref={'import': 'iata_csv', 'region': row['region'].strip()}))
        except (KeyError, ValueError, units.UnitError) as exc:
            errors.append(f'line {line}: {exc!r}')
    info = {'implied_bbl_per_mt': round(sum(implied) / len(implied), 3)} if implied else {}
    return out, errors, info
