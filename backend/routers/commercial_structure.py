import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()


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
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch
