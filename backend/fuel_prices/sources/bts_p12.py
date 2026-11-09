"""BTS Form 41 Schedule P-12(a) fuel cost and gallons — file import (download the CSV from transtats.bts.gov "Air Carrier Financial Reports" yourself).

ASSUMPTION (not verified — the field-selection page was not readable here): the exact column names. This importer therefore finds columns by pattern instead of by name:
  year / month        columns named YEAR and MONTH
  gallons and cost    columns containing GALLONS / COST (or EXPENSE); the operator class comes from SCHED vs NONSCHED (or "NON-SCHEDULED") in the name, the market from
                      DOM / INT in the name. Pass `column_map` ({"gallons_sched": "COL", "cost_sched": "COL", "gallons_nonsched": ..., "cost_nonsched": ...}) to name them yourself.
Price = sum(cost) / sum(gallons) over all carriers in the month (a volume-weighted airline-PAID price), country US, basis airline_paid. Months with no gallons are skipped.
"""

import csv
import io
import re
from collections import defaultdict
from datetime import date

from .base import Observation

SOURCE_ID = 'bts_p12'
KEYS = ('gallons_sched', 'cost_sched', 'gallons_nonsched', 'cost_nonsched')


def _classify(header: str) -> str | None:
    name = header.upper()
    kind = 'gallons' if 'GALLON' in name else 'cost' if ('COST' in name or 'EXPENSE' in name) else None
    if not kind:
        return None
    nonsched = bool(re.search(r'NON[\s_-]?SCHED', name))
    sched = (not nonsched) and 'SCHED' in name
    if nonsched:
        return f'{kind}_nonsched'
    return f'{kind}_sched' if sched else None


def detect_columns(headers: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for header in headers:
        key = _classify(header)
        if key:
            found[key].append(header)
    return found


def parse(text: str, column_map: dict | None = None) -> tuple[list[Observation], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    upper = {h.upper(): h for h in headers}
    if 'YEAR' not in upper or 'MONTH' not in upper:
        return [], ['need YEAR and MONTH columns']
    cols = {k: [v] for k, v in (column_map or {}).items() if k in KEYS} or detect_columns(headers)
    needs = [k for k in KEYS if k not in cols]
    if needs == list(KEYS):
        return [], [f'no gallons/cost columns recognised in {headers[:12]}…; pass column_map']
    totals: dict[tuple[int, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])  # (year, month, class) -> [gallons, cost]
    for row in reader:
        try:
            year, month = int(float(row[upper['YEAR']])), int(float(row[upper['MONTH']]))
        except (ValueError, KeyError):
            continue
        for cls, g_key, c_key in (('scheduled', 'gallons_sched', 'cost_sched'), ('non_scheduled', 'gallons_nonsched', 'cost_nonsched')):
            if g_key not in cols or c_key not in cols:
                continue
            gallons = sum(_num(row.get(col)) for col in cols[g_key])
            cost = sum(_num(row.get(col)) for col in cols[c_key])
            acc = totals[(year, month, cls)]
            acc[0] += gallons
            acc[1] += cost
    out = []
    for (year, month, cls), (gallons, cost) in sorted(totals.items()):
        if gallons <= 0 or cost <= 0:
            continue
        price = cost / gallons
        out.append(Observation(
            series_id=f'{SOURCE_ID}:US:{cls}', obs_date=date(year, month, 1), value_usd_per_gal=price, value_original=price, unit_original='usd_gal', currency_original='USD',
            period_type='month', geo_level='country', country_iso2='US', operator_class=cls, price_basis='airline_paid', source_id=SOURCE_ID, quality='derived',
            raw_ref={'import': 'bts_p12a', 'gallons': gallons, 'cost_usd': cost, 'formula': 'sum(cost)/sum(gallons) over carriers'}))
    return out, []


def _num(value) -> float:
    try:
        return float((value or '0').replace(',', '').strip() or 0)
    except ValueError:
        return 0.0
