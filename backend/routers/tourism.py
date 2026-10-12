"""Global Tourism & Economic Dependency — our own API (backend/tourism/). Provider URLs are fixed inside the connectors; nothing here builds an
external request from user input except registry-validated ISO codes."""

import base64
import binascii
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..tourism import constants as c
from ..tourism import exporter, registry, service

router = APIRouter(prefix='/tourism')
MAX_COUNTRIES = 300
MAX_IMPORT_BYTES = 15 * 1024 * 1024


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={'code': code, 'message': message})


def _year(value: str | None) -> int | None:
    """'latest' / empty -> None; otherwise a year 1960-2100."""
    if value is None or value.strip().lower() in ('', 'latest'):
        return None
    if not re.fullmatch(r'\d{4}', value.strip()) or not 1960 <= int(value) <= 2100:
        raise _error(422, 'invalid_year', 'year must be "latest" or a four-digit year between 1960 and 2100.')
    return int(value)


def _codes(countries: str) -> list[str]:
    codes = [part.strip().upper() for part in countries.split(',') if part.strip()]
    if not codes:
        raise _error(422, 'no_countries', 'Give at least one ISO country code in "countries".')
    if len(codes) > MAX_COUNTRIES:
        raise _error(422, 'too_many_countries', f'At most {MAX_COUNTRIES} countries per request.')
    bad = [code for code in codes if not re.fullmatch(r'[A-Z]{2,3}', code)]
    if bad:
        raise _error(422, 'invalid_country_code', 'Invalid ISO code(s): ' + ', '.join(bad[:10]))
    return codes


def _country_dict(row: models.TourismCountry, coverage: dict[str, set[str]]) -> dict:
    return {
        'country_id': row.country_id, 'country_name': row.country_name, 'iso_alpha2': row.iso_alpha2, 'iso_alpha3': row.iso_alpha3, 'region': row.region, 'subregion': row.subregion,
        'territory_status': row.territory_status, 'parent_country': row.parent_country, 'manual': row.manual,
        'un_m49': row.un_m49,
        'coverage': {'world_bank': bool(row.in_world_bank), 'unsd': row.country_id in coverage.get(c.UNSD, set()), 'wttc': row.country_id in coverage.get(c.WTTC, set()), 'idb': row.country_id in coverage.get(c.IDB, set()),
                     'statista': row.country_id in coverage.get(c.STATISTA, set())},
    }


@router.get('/countries')
def list_countries(q: str | None = None, region: str | None = None, status: str | None = Query(default=None, pattern='^(country|territory)$'), db: Session = Depends(get_db)):
    registry.seed_registry(db)
    query = db.query(models.TourismCountry)
    if region:
        query = query.filter(models.TourismCountry.region == region)
    if status:
        query = query.filter(models.TourismCountry.territory_status == status)
    rows = query.order_by(models.TourismCountry.country_name).all()
    if q:
        needle = registry.normalize_name(q)
        rows = [row for row in rows if needle in registry.normalize_name(row.country_name) or needle == row.iso_alpha2.lower() or needle == (row.iso_alpha3 or '').lower()]
    coverage: dict[str, set[str]] = {}
    for source, country_id in db.query(models.TourismObservation.data_source, models.TourismObservation.country_id).distinct().all():
        coverage.setdefault(source, set()).add(country_id)
    return {'countries': [_country_dict(row, coverage) for row in rows], 'regions': list(c.REGIONS) + (['Other'] if any(r.region == 'Other' for r in rows) else [])}


class ManualCountry(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    iso_alpha2: str = Field(min_length=2, max_length=2)
    iso_alpha3: str | None = Field(default=None, max_length=3)
    region: str
    territory: bool = False
    parent_country: str | None = Field(default=None, max_length=2)


@router.post('/countries')
def add_country(payload: ManualCountry, db: Session = Depends(get_db)):
    try:
        row = registry.add_manual_country(db, name=payload.name, iso2=payload.iso_alpha2, iso3=payload.iso_alpha3, region=payload.region, territory=payload.territory, parent=payload.parent_country)
    except ValueError as error:
        raise _error(422, 'invalid_country', str(error)) from error
    return _country_dict(row, {})


@router.get('/countries/{code}')
def country_detail(code: str, year: str | None = None, db: Session = Depends(get_db)):
    try:
        return service.detail(db, code, _year(year))
    except KeyError as error:
        raise _error(404, 'unknown_country', f'{code} is not in the country registry.') from error


@router.get('/compare')
def compare(countries: str, year: str | None = None, refresh: bool = False, db: Session = Depends(get_db)):
    return service.compare(db, _codes(countries), _year(year), refresh=refresh)


@router.get('/stored')
def stored(countries: str, year: str | None = None, db: Session = Depends(get_db)):
    """Rows built only from the database (no provider call): what the Market Analysis table shows on load."""
    return service.stored_rows(db, _codes(countries), _year(year))


class RefreshIn(BaseModel):
    countries: list[str] = Field(min_length=1, max_length=MAX_COUNTRIES)
    year: str | None = None


@router.post('/refresh')
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    """User-requested update of the stored values for these countries (calls the providers), then returns the stored rows."""
    return service.refresh_rows(db, _codes(','.join(payload.countries)), _year(payload.year))


@router.get('/history')
def history(country: str, year_from: int | None = Query(default=None, alias='from', ge=1960, le=2100), year_to: int | None = Query(default=None, alias='to', ge=1960, le=2100), db: Session = Depends(get_db)):
    if year_from and year_to and year_from > year_to:
        raise _error(422, 'invalid_range', '"from" must not be after "to".')
    try:
        return service.history(db, country.strip().upper(), year_from, year_to)
    except KeyError as error:
        raise _error(404, 'unknown_country', f'{country} is not in the country registry.') from error


@router.get('/providers/status')
def providers_status(check: bool = False, db: Session = Depends(get_db)):
    return {'providers': service.providers_status(db, check=check)}


class ProviderPatch(BaseModel):
    enabled: bool


@router.put('/providers/{provider_id}')
def patch_provider(provider_id: str, payload: ProviderPatch, db: Session = Depends(get_db)):
    service.ensure_providers(db)
    row = db.get(models.TourismProvider, provider_id.upper())
    if row is None:
        raise _error(404, 'unknown_provider', f'Unknown provider {provider_id}.')
    row.enabled = payload.enabled
    db.commit()
    return {'provider_id': row.provider_id, 'enabled': row.enabled}


@router.post('/providers/{provider_id}/sync')
def sync_provider(provider_id: str, db: Session = Depends(get_db)):
    try:
        if provider_id.upper() == c.UNSD:
            return service.sync_unsd(db, force=True)
        return service.sync_registered(db, provider_id.upper())
    except ValueError as error:
        raise _error(422, 'not_syncable', str(error)) from error


class ImportIn(BaseModel):
    provider: str = 'WTTC'
    file_name: str = Field(min_length=1, max_length=200)
    content_base64: str
    dataset_edition: str = Field(default='', max_length=120)
    unit: str = 'percent'


@router.post('/import')
def import_file(payload: ImportIn, db: Session = Depends(get_db)):
    if payload.provider.upper() != c.WTTC:
        raise _error(422, 'unsupported_provider', 'File import is only available for the WTTC provider.')
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise _error(422, 'invalid_file', 'The file data was not valid base64.') from error
    if not content or len(content) > MAX_IMPORT_BYTES:
        raise _error(422, 'invalid_file', 'The file is empty or larger than 15 MB.')
    try:
        return service.import_wttc(db, file_name=payload.file_name, content=content, edition=payload.dataset_edition, unit=payload.unit)
    except ValueError as error:
        raise _error(422, 'invalid_file', str(error)) from error


@router.get('/imports')
def list_imports(db: Session = Depends(get_db)):
    jobs = db.query(models.TourismImportJob).order_by(models.TourismImportJob.import_id.desc()).limit(50).all()
    return {'imports': [service.import_job_dict(job) for job in jobs]}


@router.get('/export')
def export(countries: str, year: str | None = None, file_format: str = Query(default='csv', alias='format', pattern='^(csv|xlsx|json)$'),
           layout: str = Query(default='wide', pattern='^(wide|long)$'), year_from: int | None = Query(default=None, alias='from'), year_to: int | None = Query(default=None, alias='to'),
           db: Session = Depends(get_db)):
    data = service.compare(db, _codes(countries), _year(year))
    if layout == 'wide':
        columns, records = exporter.wide_rows(data['rows'])
    else:
        columns, records = exporter.long_rows(db, data['rows'], year_from, year_to)
    content, media_type, extension = exporter.render(columns, records, file_format)
    return Response(content=content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="tourism-{layout}.{extension}"'})
