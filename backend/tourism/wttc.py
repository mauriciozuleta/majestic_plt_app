"""WTTC (World Travel & Tourism Council) — licensed data import.

WTTC has no verified public REST API, so the module does NOT call or scrape researchhub.wttc.org. An administrator uploads a machine-readable file
obtained under a WTTC licence (CSV or XLSX); this module normalises country names, years, indicators and units, and stores the dataset edition.
`WttcApiAdapter` is the place for a future licensed API; today it reports "not available".

Accepted layouts (headers are matched case-insensitively):
  long : country | year | indicator | value [| unit]       (indicator text naming GDP or employment, as a share)
  wide : country | year | <tourism GDP column> | <tourism employment column>
Country may be a name or an ISO alpha-2/alpha-3 code column. Only TOTAL contribution shares are accepted: a header that says "direct" (or
"induced" alone) is rejected, and so is a count of jobs, so the direct contribution is never stored as the total.
"""

import csv
import io
import re
from dataclasses import dataclass, field

from . import constants as c

COUNTRY_HEADERS = {'country', 'country name', 'country/territory', 'economy', 'geography', 'name'}
CODE_HEADERS = {'iso', 'iso2', 'iso3', 'iso code', 'iso alpha2', 'iso alpha3', 'iso_alpha2', 'iso_alpha3', 'code', 'country code'}
YEAR_HEADERS = {'year', 'reference year', 'date', 'period'}
INDICATOR_HEADERS = {'indicator', 'measure', 'series', 'metric'}
VALUE_HEADERS = {'value', 'amount', 'obs value'}
MISSING_TEXT = {'N/A', 'NA', '-', '..', 'NAN'}


@dataclass
class ParsedFile:
    rows: list[dict] = field(default_factory=list)  # {country_text, code_text, year, indicator, value_text, source_row}
    rejected: list[dict] = field(default_factory=list)  # {row, reason}


def read_table(file_name: str, content: bytes) -> list[list]:
    name = file_name.lower()
    if name.endswith('.xlsx') or name.endswith('.xlsm'):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        return [list(row) for row in workbook.active.iter_rows(values_only=True)]
    if name.endswith('.csv') or name.endswith('.txt'):
        text = content.decode('utf-8-sig', errors='replace')
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        return list(csv.reader(io.StringIO(text), dialect))
    raise ValueError('Only CSV and XLSX files are supported.')


def classify_indicator(text: str) -> str | None:
    """TOURISM_GDP_TOTAL_PCT / TOURISM_EMPLOYMENT for a TOTAL-contribution share, None for anything else (direct-only, job counts, other measures)."""
    lowered = re.sub(r'\s+', ' ', (text or '').lower())
    if not lowered:
        return None
    if 'direct' in lowered and 'total' not in lowered and 'indirect' not in lowered:
        return None
    if 'induced' in lowered and 'total' not in lowered:
        return None
    is_share = any(word in lowered for word in ('%', 'share', 'percent', 'pct', 'of gdp', 'of total employment', 'of employment'))
    if 'gdp' in lowered and is_share and any(word in lowered for word in ('tourism', 'travel', 'total')):
        return c.TOURISM_GDP_TOTAL
    if ('employment' in lowered or 'jobs' in lowered) and is_share and any(word in lowered for word in ('tourism', 'travel', 'total')):
        return c.TOURISM_EMPLOYMENT
    return None


def _year(value) -> int | None:
    text = str(value).strip() if value is not None else ''
    match = re.match(r'^(\d{4})', text)
    if match:
        return int(match.group(1))
    try:
        return int(float(text))
    except ValueError:
        return None


def parse(file_name: str, content: bytes) -> ParsedFile:
    table = [row for row in read_table(file_name, content) if any(cell not in (None, '') for cell in row)]
    result = ParsedFile()
    if len(table) < 2:
        result.rejected.append({'row': 0, 'reason': 'The file has no data rows.'})
        return result
    headers = [str(cell).strip() if cell is not None else '' for cell in table[0]]
    lowered = [header.lower() for header in headers]

    def find(options: set[str]) -> int | None:
        return next((i for i, header in enumerate(lowered) if header in options), None)

    country_col, code_col, year_col = find(COUNTRY_HEADERS), find(CODE_HEADERS), find(YEAR_HEADERS)
    if year_col is None or (country_col is None and code_col is None):
        result.rejected.append({'row': 1, 'reason': 'Headers not recognised: a country (or ISO code) column and a year column are required.'})
        return result
    indicator_col, value_col = find(INDICATOR_HEADERS), find(VALUE_HEADERS)
    wide: dict[int, str] = {}
    if indicator_col is None or value_col is None:
        for i, header in enumerate(headers):
            if i in (country_col, code_col, year_col):
                continue
            kind = classify_indicator(header)
            if kind:
                wide[i] = kind
        if not wide:
            result.rejected.append({'row': 1, 'reason': 'No total-contribution GDP/employment share column found. Direct-only columns and job counts are not accepted.'})
            return result
    for number, row in enumerate(table[1:], start=2):
        cells = list(row) + [None] * (len(headers) - len(row))
        country_text = str(cells[country_col]).strip() if country_col is not None and cells[country_col] is not None else ''
        code_text = str(cells[code_col]).strip().upper() if code_col is not None and cells[code_col] is not None else ''
        year = _year(cells[year_col])
        if year is None:
            result.rejected.append({'row': number, 'reason': f'Year "{cells[year_col]}" is not a year.'})
            continue
        if indicator_col is not None and value_col is not None:
            kind = classify_indicator(str(cells[indicator_col] or ''))
            if kind is None:
                result.rejected.append({'row': number, 'reason': f'Indicator "{cells[indicator_col]}" is not a total tourism GDP/employment share.'})
                continue
            targets = [(kind, cells[value_col])]
        else:
            targets = [(kind, cells[i]) for i, kind in wide.items()]
        for kind, raw in targets:
            if raw in (None, '') or str(raw).strip().upper() in MISSING_TEXT:
                continue
            result.rows.append({'country_text': country_text, 'code_text': code_text, 'year': year, 'indicator': kind,
                                'value_text': str(raw).strip().replace('%', '').replace(',', ''), 'source_row': number})
    return result


class WttcApiAdapter:
    """Placeholder for a future licensed WTTC API. Nothing is fabricated: there is no verified public endpoint."""

    available = False
    reason = 'WTTC has no verified general-purpose public API. Import a licensed CSV/XLSX file instead.'
