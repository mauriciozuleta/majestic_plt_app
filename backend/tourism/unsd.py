"""United Nations Statistics Division — SDG API connector (https://unstats.un.org/SDGAPI/swagger/, no key).

Series ST_GDP_ZS = SDG indicator 8.9.1, "Tourism direct GDP as a proportion of total GDP (%)". It feeds TOURISM_GDP_DIRECT_PCT only: the direct
contribution is never presented as WTTC's total contribution.

Behaviour verified against the live API (2026-10):
  * GET /v1/sdg/Series/Data?seriesCode=ST_GDP_ZS&pageSize=N&page=P  -> {size, totalElements, totalPages, pageNumber, data: [...]}; pageSize up to at least 2000.
    Each record: geoAreaCode (M49, as text), geoAreaName, timePeriodStart (float year, e.g. 2008.0), value (text), source (reporting agency), footnotes [..],
    attributes {Nature, Units: 'PERCENT'}, dimensions {'Reporting Type': 'G'}. 1,669 records, 149 areas (about 125 countries/territories + aggregates), 2008-2024.
  * GET /v1/sdg/Series/ST_GDP_ZS/GeoArea/{m49}/DataSlice -> {series, geoAreaCode, geoAreaName, dimensions: [{value, timePeriodStart, 'Reporting Type'}]};
    an area without observations answers 200 with `dimensions: []`; an unknown area code answers 500.
  * GET /v1/sdg/GeoArea/List -> [{geoAreaCode, geoAreaName}] (460 areas incl. regions); it carries NO ISO codes, so the ISO <-> M49 link is made by matching
    names against the registry (registry.assign_m49) and is stored on the country row.
Aggregates (World, regions, LDCs, SIDS …) are in the data; they never match a registry country and are ignored.
"""

from . import http
from .constants import TOURISM_GDP_DIRECT, UNSD_SERIES

BASE_URL = 'https://unstats.un.org/SDGAPI/v1/sdg'
PAGE_SIZE = 2000
SERIES = UNSD_SERIES[TOURISM_GDP_DIRECT]
DATASET = 'SDG Indicator 8.9.1 — Tourism direct GDP as a proportion of total GDP (series ST_GDP_ZS)'
METHODOLOGY = 'Direct contribution of tourism only (tourism direct GDP / total GDP). It is not the total contribution published by WTTC.'


def series_url() -> str:
    return f'{BASE_URL}/Series/Data?seriesCode={SERIES}'


def area_url(m49: str) -> str:
    """The documented single-area route, used as the observation's source link."""
    return f'{BASE_URL}/Series/{SERIES}/GeoArea/{m49}/DataSlice'


def fetch_geo_areas() -> list[dict]:
    """[{code, name}] of every UN area (countries, territories, regions)."""
    data = http.get_json(f'{BASE_URL}/GeoArea/List', ttl_hours=24 * 7)
    if not isinstance(data, list):
        raise http.ProviderError('Unexpected UNSD GeoArea/List answer.')
    return [{'code': str(item['geoAreaCode']), 'name': item['geoAreaName']} for item in data if item.get('geoAreaCode') is not None and item.get('geoAreaName')]


def _year(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_record(record: dict) -> dict | None:
    """One bulk-API record -> {m49, name, year, value_text, agency, nature, footnotes, units, reporting_type}; None when it carries no usable observation."""
    year = _year(record.get('timePeriodStart'))
    value = record.get('value')
    if year is None or value in (None, ''):
        return None
    attributes = record.get('attributes') or {}
    dimensions = record.get('dimensions') or {}
    return {
        'm49': str(record.get('geoAreaCode')), 'name': record.get('geoAreaName') or '', 'year': year, 'value_text': str(value).strip(),
        'agency': (record.get('source') or '').strip(), 'nature': attributes.get('Nature'), 'units': attributes.get('Units'),
        'footnotes': [note for note in (record.get('footnotes') or []) if note], 'reporting_type': dimensions.get('Reporting Type'),
    }


def fetch_series_rows() -> tuple[list[dict], dict]:
    """Every record of the series, following the pagination. Returns (normalized rows, {'total': n, 'pages': n, 'dropped': n})."""
    rows: list[dict] = []
    dropped = 0
    page = 1
    total = pages = 0
    while True:
        data = http.get_json(f'{BASE_URL}/Series/Data', {'seriesCode': SERIES, 'pageSize': PAGE_SIZE, 'page': page})
        if not isinstance(data, dict) or not isinstance(data.get('data'), list):
            raise http.ProviderError('Unexpected UNSD answer: no data list.')
        total, pages = int(data.get('totalElements', 0)), int(data.get('totalPages', 1))
        for record in data['data']:
            row = normalize_record(record)
            if row is None:
                dropped += 1
            else:
                rows.append(row)
        if page >= pages or not data['data']:
            break
        page += 1
    if total == 0:
        raise http.ProviderError(f'UNSD returned no observations for {SERIES}.')
    return rows, {'total': total, 'pages': pages, 'dropped': dropped}


def fetch_area(m49: str) -> list[dict]:
    """The slice of one area: [{year, value_text, reporting_type}]. Empty when the area reports nothing. A 500 (unknown area) becomes ProviderError."""
    data = http.get_json(f'{BASE_URL}/Series/{SERIES}/GeoArea/{m49}/DataSlice', ttl_hours=24)
    if not isinstance(data, dict) or 'dimensions' not in data:
        raise http.ProviderError('Unexpected UNSD DataSlice answer.')
    out = []
    for item in data['dimensions']:
        year = _year(item.get('timePeriodStart'))
        if year is None or item.get('value') in (None, ''):
            continue
        out.append({'year': year, 'value_text': str(item['value']).strip(), 'reporting_type': item.get('Reporting Type')})
    return out
