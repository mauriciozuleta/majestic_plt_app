import csv
import uuid
from io import StringIO

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()

OPENFLIGHTS_AIRPORTS_URL = 'https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat'


def _lookup_airport_by_iata(iata_code: str) -> dict | None:
    iata = iata_code.strip().upper()
    if not iata or len(iata) != 3:
        return None

    try:
        response = httpx.get(OPENFLIGHTS_AIRPORTS_URL, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    reader = csv.reader(StringIO(response.text))
    for fields in reader:
        if len(fields) <= 8 or fields[4].strip('"').upper() != iata:
            continue
        try:
            name = fields[1].strip('"')
            city = fields[2].strip('"')
            country = fields[3].strip('"')
            latitude = float(fields[6]) if fields[6] else None
            longitude = float(fields[7]) if fields[7] else None
            altitude_ft = float(fields[8]) if fields[8] and fields[8] != '\\N' else None
        except (ValueError, IndexError):
            continue
        if all([latitude is not None, longitude is not None, altitude_ft is not None, name, city, country]):
            return {
                'name': name,
                'city': city,
                'country': country,
                'latitude': latitude,
                'longitude': longitude,
                'altitude_ft': altitude_ft,
            }
    return None


class CommercialRegionCreate(BaseModel):
    name: str
    manager_name: str | None = None
    user_name: str | None = None


class CommercialCountryCreate(BaseModel):
    region_id: str
    name: str
    country_code: str | None = None
    currency: str | None = None
    currency_code: str | None = None
    manager_name: str | None = None
    user_name: str | None = None


class CommercialBranchCreate(BaseModel):
    country_id: str
    name: str
    manager_name: str | None = None
    user_name: str | None = None
    airport: str | None = None
    active: str = 'active'
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_ft: float | None = None
    fuel_cost_gl: float | None = None
    cargo_handling_cost_kg: float | None = None
    airport_fee: float | None = None
    turnaround_cost: float | None = None
    other_desc: str | None = None
    other_cost: float | None = None


class CommercialBranchUpdate(CommercialBranchCreate):
    country_id: str | None = None
    name: str | None = None


class CommercialRegionUpdate(BaseModel):
    manager_name: str | None = None
    user_name: str | None = None


class CommercialCountryUpdate(BaseModel):
    manager_name: str | None = None
    user_name: str | None = None


class CommercialRegionOut(CommercialRegionCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class CommercialCountryOut(CommercialCountryCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class CommercialBranchOut(CommercialBranchCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class CountryReferenceOut(BaseModel):
    id: str
    name: str
    country_code: str
    currency: str
    currency_code: str
    region: str

    class Config:
        from_attributes = True


@router.get('/reference-regions', response_model=list[str])
def list_reference_regions(db: Session = Depends(get_db)):
    rows = (
        db.query(models.CountryReferenceCatalog.region)
        .filter(models.CountryReferenceCatalog.region.isnot(None))
        .filter(models.CountryReferenceCatalog.region != '')
        .distinct()
        .order_by(models.CountryReferenceCatalog.region)
        .all()
    )
    return [row[0] for row in rows]


@router.get('/reference-countries', response_model=list[CountryReferenceOut])
def list_reference_countries(region: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(models.CountryReferenceCatalog)
    if region:
        query = query.filter(models.CountryReferenceCatalog.region == region)
    return query.order_by(models.CountryReferenceCatalog.name).all()


@router.get('/airport-lookup')
def airport_lookup(iata_code: str = Query(...)):
    iata = iata_code.strip().upper()
    if not iata or len(iata) != 3:
        raise HTTPException(status_code=400, detail='Invalid IATA code')

    result = _lookup_airport_by_iata(iata)
    if not result:
        raise HTTPException(status_code=404, detail='Airport not found')
    return result


@router.get('/companies/{company_id}/commercial-regions', response_model=list[CommercialRegionOut])
def list_regions(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.CommercialRegion).filter_by(company_id=company_id).all()


@router.post('/companies/{company_id}/commercial-regions', response_model=CommercialRegionOut)
def create_region(company_id: str, payload: CommercialRegionCreate, db: Session = Depends(get_db)):
    region = models.CommercialRegion(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name=payload.name,
        manager_name=payload.manager_name,
        user_name=payload.user_name,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


@router.put('/companies/{company_id}/commercial-regions/{region_id}', response_model=CommercialRegionOut)
def update_region(company_id: str, region_id: str, payload: CommercialRegionUpdate, db: Session = Depends(get_db)):
    region = db.query(models.CommercialRegion).filter_by(id=region_id, company_id=company_id).first()
    if not region:
        raise HTTPException(status_code=404, detail='Region not found')

    region.manager_name = payload.manager_name
    region.user_name = payload.user_name
    db.commit()
    db.refresh(region)
    return region


@router.get('/companies/{company_id}/commercial-countries', response_model=list[CommercialCountryOut])
def list_countries(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.CommercialCountry).filter_by(company_id=company_id).all()


@router.post('/companies/{company_id}/commercial-countries', response_model=CommercialCountryOut)
def create_country(company_id: str, payload: CommercialCountryCreate, db: Session = Depends(get_db)):
    region = db.query(models.CommercialRegion).filter_by(id=payload.region_id, company_id=company_id).first()
    if not region:
        raise HTTPException(status_code=404, detail='Region not found')

    reference_country = None
    if payload.country_code:
        reference_country = db.query(models.CountryReferenceCatalog).filter_by(country_code=payload.country_code).first()
    if not reference_country and payload.name:
        reference_country = db.query(models.CountryReferenceCatalog).filter_by(name=payload.name).first()

    resolved_country_name = reference_country.name if reference_country else payload.name
    resolved_country_code = payload.country_code or (reference_country.country_code if reference_country else None)
    resolved_currency = payload.currency or (reference_country.currency if reference_country else None)
    resolved_currency_code = payload.currency_code or (reference_country.currency_code if reference_country else None)

    country = models.CommercialCountry(
        id=str(uuid.uuid4()),
        company_id=company_id,
        region_id=payload.region_id,
        name=resolved_country_name,
        country_code=resolved_country_code,
        currency=resolved_currency,
        currency_code=resolved_currency_code,
        manager_name=payload.manager_name,
        user_name=payload.user_name,
    )
    db.add(country)
    db.commit()
    db.refresh(country)
    return country


@router.put('/companies/{company_id}/commercial-countries/{country_id}', response_model=CommercialCountryOut)
def update_country(company_id: str, country_id: str, payload: CommercialCountryUpdate, db: Session = Depends(get_db)):
    country = db.query(models.CommercialCountry).filter_by(id=country_id, company_id=company_id).first()
    if not country:
        raise HTTPException(status_code=404, detail='Country not found')

    country.manager_name = payload.manager_name
    country.user_name = payload.user_name
    db.commit()
    db.refresh(country)
    return country


@router.delete('/companies/{company_id}/commercial-countries/{country_id}', status_code=204)
def delete_country(company_id: str, country_id: str, db: Session = Depends(get_db)):
    country = db.query(models.CommercialCountry).filter_by(id=country_id, company_id=company_id).first()
    if not country:
        raise HTTPException(status_code=404, detail='Country not found')

    # A branch orphaned by its country would break the chart/selection
    # logic elsewhere, so its branches go with it.
    db.query(models.CommercialBranch).filter_by(country_id=country_id, company_id=company_id).delete()
    db.delete(country)
    db.commit()


@router.get('/companies/{company_id}/commercial-branches', response_model=list[CommercialBranchOut])
def list_branches(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.CommercialBranch).filter_by(company_id=company_id).all()


@router.post('/companies/{company_id}/commercial-branches', response_model=CommercialBranchOut)
def create_branch(company_id: str, payload: CommercialBranchCreate, db: Session = Depends(get_db)):
    country = db.query(models.CommercialCountry).filter_by(id=payload.country_id, company_id=company_id).first()
    if not country:
        raise HTTPException(status_code=404, detail='Country not found')

    branch = models.CommercialBranch(
        id=str(uuid.uuid4()),
        company_id=company_id,
        country_id=payload.country_id,
        name=payload.name,
        manager_name=payload.manager_name,
        user_name=payload.user_name,
        airport=payload.airport,
        active=payload.active,
        city=payload.city,
        latitude=payload.latitude,
        longitude=payload.longitude,
        altitude_ft=payload.altitude_ft,
        fuel_cost_gl=payload.fuel_cost_gl,
        cargo_handling_cost_kg=payload.cargo_handling_cost_kg,
        airport_fee=payload.airport_fee,
        turnaround_cost=payload.turnaround_cost,
        other_desc=payload.other_desc,
        other_cost=payload.other_cost,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.put('/companies/{company_id}/commercial-branches/{branch_id}', response_model=CommercialBranchOut)
def update_branch(company_id: str, branch_id: str, payload: CommercialBranchUpdate, db: Session = Depends(get_db)):
    branch = db.query(models.CommercialBranch).filter_by(id=branch_id, company_id=company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail='Branch not found')

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(branch, field, value)

    db.commit()
    db.refresh(branch)
    return branch


@router.delete('/companies/{company_id}/commercial-branches/{branch_id}', status_code=204)
def delete_branch(company_id: str, branch_id: str, db: Session = Depends(get_db)):
    branch = db.query(models.CommercialBranch).filter_by(id=branch_id, company_id=company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail='Branch not found')

    db.delete(branch)
    db.commit()
