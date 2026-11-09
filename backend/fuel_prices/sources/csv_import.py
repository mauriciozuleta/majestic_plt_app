"""Manual CSV import: the way country- and airport-level prices (and the IATA regional index) get in until a licensed feed exists.

Columns (header names, case-insensitive):
  required  obs_date (YYYY-MM-DD), value, unit (usd_gal | usd_bbl | cts_gal | usd_mt | usd_litre | local_per_litre | local_per_gal), geo_level, operator_class, price_basis
  by level  region_code (region), country_iso2 (country, airport), airport_iata (airport)
  optional  period_type (day|week|month, default day), currency (default USD), fx_to_usd (REQUIRED for local_* units; the rate is stored), quality (default manual),
            confidence (0-1), series_id (default derived from level/place/class/basis)
Every row is validated before anything is written: one bad row rejects the whole file with the list of problems. Re-importing the same file changes nothing.
"""

import csv
import io
from datetime import date

from .. import config as c
from .. import units
from .base import Observation

REQUIRED = ('obs_date', 'value', 'unit', 'geo_level', 'operator_class', 'price_basis')


def parse(text: str, source_id: str) -> tuple[list[Observation], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ['the file is empty']
    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
    missing = [col for col in REQUIRED if col not in reader.fieldnames]
    if missing:
        return [], [f'missing columns: {", ".join(missing)}']
    out: list[Observation] = []
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        row = {k: (v or '').strip() for k, v in row.items() if k}
        try:
            out.append(_row(row, source_id))
        except (ValueError, units.UnitError) as exc:
            errors.append(f'line {line}: {exc}')
    return out, errors


def _row(row: dict, source_id: str) -> Observation:
    level, cls, basis = row['geo_level'].lower(), row['operator_class'].lower(), row['price_basis'].lower()
    if level not in c.GEO_LEVELS:
        raise ValueError(f'geo_level {level!r} not in {c.GEO_LEVELS}')
    if cls not in c.OPERATOR_CLASSES:
        raise ValueError(f'operator_class {cls!r} not in {c.OPERATOR_CLASSES}')
    if basis not in c.PRICE_BASES:
        raise ValueError(f'price_basis {basis!r} not in {c.PRICE_BASES}')
    iso2 = row.get('country_iso2', '').upper() or None
    iata = row.get('airport_iata', '').upper() or None
    region = row.get('region_code', '').upper() or None
    if level == 'airport' and not (iata and len(iata) == 3 and iso2):
        raise ValueError('airport rows need a 3-letter airport_iata and country_iso2')
    if level == 'country' and not (iso2 and len(iso2) == 2):
        raise ValueError('country rows need a 2-letter country_iso2')
    if level == 'region' and not region:
        raise ValueError('region rows need region_code')
    obs_date = date.fromisoformat(row['obs_date'])
    value = float(row['value'])
    if value <= 0:
        raise ValueError('value must be positive')
    unit = row['unit'].lower()
    fx = float(row['fx_to_usd']) if row.get('fx_to_usd') else None
    usd = units.to_usd_per_gal(value, unit, fx_to_usd=fx)
    if not 0.05 <= usd <= 20:
        raise ValueError(f'{usd:.3f} USD/gal is outside the plausible range (0.05-20): check the unit')
    period = (row.get('period_type') or 'day').lower()
    if period not in ('day', 'week', 'month'):
        raise ValueError(f'period_type {period!r}')
    quality = (row.get('quality') or 'manual').lower()
    if quality not in c.QUALITIES:
        raise ValueError(f'quality {quality!r}')
    confidence = float(row['confidence']) if row.get('confidence') else None
    place = iata or iso2 or region or 'global'
    series_id = row.get('series_id') or f'{source_id}:{level}:{place}:{cls}:{basis}'
    raw = {'import': 'csv'}
    if fx:
        raw['fx_to_usd'] = fx
    return Observation(
        series_id=series_id, obs_date=obs_date, value_usd_per_gal=usd, geo_level=level, price_basis=basis, source_id=source_id, operator_class=cls, period_type=period,
        value_original=value, unit_original=unit, currency_original=(row.get('currency') or 'USD').upper(), region_code=region, country_iso2=iso2, airport_iata=iata,
        quality=quality, confidence=confidence, raw_ref=raw)
