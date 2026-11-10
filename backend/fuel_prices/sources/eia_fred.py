"""RESTRICTED — do not use as a source. FRED's terms bar scraping and storing its content in a database, so this adapter is no longer registered in `ADAPTERS`, the source row is
marked `restricted` (cannot be enabled) and any rows it once stored are purged by service.seed. The file stays only as a record and as parser fixtures for the tests.
The same EIA series come straight from EIA through sources/eia_api.py.
"""

import csv
import io
from datetime import date

from .. import units
from .base import Observation

SOURCE_ID = 'eia_fred'

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
        if not raw or raw == '.':
            continue
        value = float(raw)
        is_jet = kind == 'price'
        out.append(Observation(
            series_id=f'{SOURCE_ID}:{fred_id}', obs_date=date.fromisoformat(row['observation_date']), value_usd_per_gal=units.to_usd_per_gal(value, unit), value_original=value,
            unit_original=unit, currency_original='USD', period_type=period, geo_level='country' if is_jet else 'global', country_iso2='US' if is_jet else None,
            operator_class='scheduled' if is_jet else 'unspecified', price_basis=basis, source_id=SOURCE_ID, series_kind=kind, driver_code=driver,
            raw_ref={'fred_series': fred_id, 'origin': 'EIA'}))
    return out
