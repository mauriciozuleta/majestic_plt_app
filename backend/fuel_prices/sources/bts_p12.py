"""BTS Form 41 Schedule P-12(a) MONTHLY fuel cost and gallons — file import via the drop folder (see service.scan_drop_folder), or POST /import/bts.

Automatic scheduled summary retrieval lives in bts_monthly.py. This module retains the optional CSV/drop-folder fallback for user-supplied files.

Column mapping is EXPLICIT (column_map.json in the drop folder, or the `column_map` argument). Two shapes:
  generic  {"year": "YEAR", "month": "MONTH", "gallons": ["COL"...], "cost": ["COL"...], "operator_class": "scheduled",
            "carrier_column": "CARRIER" (optional), "carrier_exclude": ["All Majors", ...] (optional: aggregate rows that would double count)}
  split    {"gallons_sched": "COL", "cost_sched": "COL", "gallons_nonsched": "COL", "cost_nonsched": "COL"}   (one file with both classes)
Without a map the importer falls back to guessing (columns containing GALLONS / COST with SCHED or NONSCHED in the name) and says so in the result.
Price = sum(cost) / sum(gallons) over the rows of the month: a volume-weighted airline-PAID price, country US, quality 'derived'. The TranStats column names are NOT verified.
"""

import csv
import io
import re
from collections import defaultdict
from datetime import date

from .base import Observation

SOURCE_ID = 'bts_p12'
SPLIT_KEYS = ('gallons_sched', 'cost_sched', 'gallons_nonsched', 'cost_nonsched')


def _classify(header: str) -> str | None:
    name = header.upper()
    kind = 'gallons' if 'GALLON' in name else 'cost' if ('COST' in name or 'EXPENSE' in name) else None
    if not kind:
        return None
    if re.search(r'NON[\s_-]?SCHED', name):
        return f'{kind}_nonsched'
    return f'{kind}_sched' if 'SCHED' in name else None


def detect_columns(headers: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for header in headers:
        key = _classify(header)
        if key:
            found[key].append(header)
    return found


def _as_list(value) -> list[str]:
    return [value] if isinstance(value, str) else list(value or [])


def parse(text: str, column_map: dict | None = None) -> tuple[list[Observation], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    cmap = column_map or {}
    year_col = cmap.get('year') or next((h for h in headers if h.upper() == 'YEAR'), None)
    month_col = cmap.get('month') or next((h for h in headers if h.upper() == 'MONTH'), None)
    if year_col not in headers or month_col not in headers:
        return [], [f'year/month columns not found (looked for {year_col!r}, {month_col!r}) in {headers[:12]}']
    # list of (operator_class, gallons columns, cost columns)
    plan: list[tuple[str, list[str], list[str]]] = []
    if cmap.get('gallons') and cmap.get('cost'):
        cls = cmap.get('operator_class', 'scheduled')
        if cls not in ('scheduled', 'non_scheduled'):
            return [], ['operator_class in the column map must be scheduled or non_scheduled']
        plan.append((cls, _as_list(cmap['gallons']), _as_list(cmap['cost'])))
    else:
        cols = {k: _as_list(v) for k, v in cmap.items() if k in SPLIT_KEYS} or detect_columns(headers)
        for cls, g, c in (('scheduled', 'gallons_sched', 'cost_sched'), ('non_scheduled', 'gallons_nonsched', 'cost_nonsched')):
            if g in cols and c in cols:
                plan.append((cls, cols[g], cols[c]))
    if not plan:
        return [], [f'no gallons/cost columns found in {headers[:12]}; give an explicit column_map']
    missing = [c for _, g, cost in plan for c in g + cost if c not in headers]
    if missing:
        return [], [f'mapped columns not in the file: {missing}']
    carrier_col = cmap.get('carrier_column')
    exclude = {x.strip().lower() for x in cmap.get('carrier_exclude', [])}
    totals: dict[tuple[int, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in reader:
        try:
            year, month = int(float(row[year_col])), int(float(row[month_col]))
        except (ValueError, KeyError, TypeError):
            continue
        if carrier_col and (row.get(carrier_col) or '').strip().lower() in exclude:
            continue
        for cls, g_cols, c_cols in plan:
            acc = totals[(year, month, cls)]
            acc[0] += sum(_num(row.get(col)) for col in g_cols)
            acc[1] += sum(_num(row.get(col)) for col in c_cols)
    out = []
    for (year, month, cls), (gallons, cost) in sorted(totals.items()):
        if gallons <= 0 or cost <= 0 or not 1 <= month <= 12:
            continue
        price = cost / gallons
        out.append(Observation(
            series_id=f'{SOURCE_ID}:US:{cls}', obs_date=date(year, month, 1), value_usd_per_gal=price, value_original=price, unit_original='usd_gal', currency_original='USD',
            period_type='month', geo_level='country', country_iso2='US', operator_class=cls, price_basis='airline_paid', source_id=SOURCE_ID, quality='derived',
            raw_ref={'import': 'bts_p12a', 'gallons': gallons, 'cost_usd': cost, 'formula': 'sum(cost)/sum(gallons)', 'explicit_column_map': bool(column_map)}))
    if not out:
        return [], ['no month with both gallons and cost > 0 was found']
    return out, []


def _num(value) -> float:
    try:
        return float((value or '0').replace(',', '').replace('$', '').strip() or 0)
    except ValueError:
        return 0.0
