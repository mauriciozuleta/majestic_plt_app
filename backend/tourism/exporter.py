"""CSV / XLSX / JSON export of the comparison, in two layouts: one row per country ('wide') and one row per country-year-indicator ('long')."""

import csv
import io
import json

from sqlalchemy.orm import Session

from .. import models
from . import constants as c
from . import service

WIDE_FIELDS = ('value', 'unit', 'year', 'source', 'dataset', 'edition', 'retrieved_at', 'status', 'reason')
LONG_COLUMNS = ['country', 'iso_alpha2', 'iso_alpha3', 'region', 'territory_status', 'indicator_code', 'indicator', 'reference_year', 'value', 'unit', 'data_source',
                'source_dataset', 'dataset_edition', 'source_url', 'data_retrieved_at', 'is_estimated', 'is_calculated', 'data_quality_status', 'methodology_note']


def wide_rows(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Every indicator (the five plus GDP) as a group of columns: value, unit, year, source, dataset, edition, retrieved_at, status, reason."""
    columns = ['country', 'iso_alpha2', 'iso_alpha3', 'region', 'territory_status', 'parent_country']
    for code in (*c.DISPLAY_INDICATORS, c.GDP_USD):
        columns.extend(f'{code}_{field}' for field in WIDE_FIELDS)
    out = []
    for row in rows:
        record = {k: row.get(k) for k in ('country', 'iso_alpha2', 'iso_alpha3', 'region', 'territory_status', 'parent_country')}
        for code in (*c.DISPLAY_INDICATORS, c.GDP_USD):
            cell = row['indicators'][code]
            for field in WIDE_FIELDS:
                record[f'{code}_{field}'] = cell.get('value_text' if field == 'value' else field)
        out.append(record)
    return columns, out


def long_rows(db: Session, rows: list[dict], year_from: int | None, year_to: int | None) -> tuple[list[str], list[dict]]:
    """Every stored observation (all sources and editions, so nothing is hidden) of the selected countries within the year range."""
    out = []
    for row in rows:
        query = db.query(models.TourismObservation).filter_by(country_id=row['country_id']).order_by(models.TourismObservation.indicator_code, models.TourismObservation.reference_year)
        for obs in query.all():
            if (year_from is not None and obs.reference_year < year_from) or (year_to is not None and obs.reference_year > year_to):
                continue
            out.append({
                'country': row['country'], 'iso_alpha2': row['iso_alpha2'], 'iso_alpha3': row['iso_alpha3'], 'region': row['region'], 'territory_status': row['territory_status'],
                'indicator_code': obs.indicator_code, 'indicator': c.INDICATORS[obs.indicator_code].label, 'reference_year': obs.reference_year, 'value': obs.value_text, 'unit': obs.unit,
                'data_source': obs.data_source, 'source_dataset': obs.source_dataset, 'dataset_edition': obs.dataset_edition or None, 'source_url': obs.source_url,
                'data_retrieved_at': obs.data_retrieved_at, 'is_estimated': obs.is_estimated, 'is_calculated': obs.is_calculated,
                'data_quality_status': service.effective_status(obs), 'methodology_note': obs.methodology_note,
            })
    return LONG_COLUMNS, out


def render(columns: list[str], records: list[dict], file_format: str) -> tuple[bytes, str, str]:
    """(content, media type, extension)."""
    if file_format == 'json':
        return json.dumps(records, ensure_ascii=False, indent=2, default=str).encode('utf-8'), 'application/json', 'json'
    if file_format == 'csv':
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
        return buffer.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8', 'csv'
    if file_format == 'xlsx':
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Tourism'
        sheet.append(columns)
        for record in records:
            sheet.append([record.get(column) for column in columns])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'
    raise ValueError('format must be csv, xlsx or json.')
