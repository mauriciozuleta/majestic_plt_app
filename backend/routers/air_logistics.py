"""Aircraft database, selected fleet and per-company charter providers.

Majestic Cargo manages the aircraft database and fleet selection; provider
forms may use any aircraft in that database. Source import is an explicit CLI job.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..aircraft_catalog import aircraft_company_id, uses_fleet_selection
from ..charter_defaults import add_majestic_providers

router = APIRouter()

PROVIDER_TYPES = {'charter', 'acmi', 'by_kg'}


class AircraftIn(BaseModel):
    manufacturer: str
    model: str
    short_name: str
    mtow_kg: float
    mldgw_kg: float | None = None
    max_ramp_kg: float | None = None
    empty_weight_kg: float
    max_payload_kg: float
    zero_fuel_kg: float
    fuel_capacity_gal: float
    fuel_burn_gal_hr: float
    min_fuel_landed_gal: float | None = None
    min_fuel_alternate_gal: float | None = None
    cargo_positions_main_deck: int
    cargo_positions_lower_deck: int
    cruise_speed_kt: float
    max_range_at_max_payload_nm: float | None = None
    max_range_with_max_fuel_nm: float | None = None


class AircraftOut(AircraftIn):
    id: str
    company_id: str
    created_at: str
    in_fleet: bool
    source_aircraft_id: str | None = None

    class Config:
        from_attributes = True


class CharterProviderIn(BaseModel):
    name: str
    country_name: str
    main_base_iata: str | None = None
    main_base_name: str | None = None
    main_base_city: str | None = None
    main_base_country: str | None = None
    aircraft_id: str
    block_hour_cost: float | None = None
    provider_type: str


class CharterProviderOut(CharterProviderIn):
    id: str
    company_id: str
    created_at: str
    source_company_id: str | None = None

    class Config:
        from_attributes = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_aircraft(payload: AircraftIn) -> dict:
    data = payload.model_dump()
    for field in ('manufacturer', 'model', 'short_name'):
        data[field] = data[field].strip()
        if not data[field]:
            raise HTTPException(status_code=400, detail=f'{field.replace("_", " ").capitalize()} is required.')
    return data


def _clean_provider(db: Session, company_id: str, payload: CharterProviderIn, allow_incomplete: bool = False) -> dict:
    data = payload.model_dump()
    data['name'] = data['name'].strip()
    data['country_name'] = data['country_name'].strip()
    data['main_base_iata'] = (data['main_base_iata'] or '').strip().upper() or None
    if not data['name']:
        raise HTTPException(status_code=400, detail='Name is required.')
    if not data['country_name']:
        raise HTTPException(status_code=400, detail='Country is required.')
    if (data['main_base_iata'] and len(data['main_base_iata']) != 3) or (not data['main_base_iata'] and not allow_incomplete):
        raise HTTPException(status_code=400, detail='Main base must be a 3-letter IATA airport code.')
    if data['provider_type'] not in PROVIDER_TYPES:
        raise HTTPException(status_code=400, detail="Type must be 'charter', 'acmi' or 'by_kg'.")
    if data['block_hour_cost'] is None and not allow_incomplete:
        raise HTTPException(status_code=400, detail='Block hour cost is required.')
    if data['block_hour_cost'] is not None and data['block_hour_cost'] < 0:
        raise HTTPException(status_code=400, detail='Block hour cost cannot be negative.')
    aircraft = db.query(models.LogisticsAircraft).filter_by(id=data['aircraft_id'], company_id=aircraft_company_id(db, company_id)).first()
    if not aircraft:
        raise HTTPException(status_code=400, detail='Choose an aircraft from this company’s aircraft list.')
    return data


@router.get('/companies/{company_id}/air-logistics/aircraft', response_model=list[AircraftOut])
def list_aircraft(company_id: str, db: Session = Depends(get_db)):
    query = db.query(models.LogisticsAircraft).filter_by(company_id=aircraft_company_id(db, company_id))
    if uses_fleet_selection(db, company_id):
        query = query.filter_by(in_fleet=True)
    return query.order_by(models.LogisticsAircraft.manufacturer, models.LogisticsAircraft.model).all()


@router.get('/companies/{company_id}/air-logistics/aircraft-catalogue', response_model=list[AircraftOut])
def list_aircraft_catalogue(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.LogisticsAircraft).filter_by(company_id=aircraft_company_id(db,company_id)).order_by(models.LogisticsAircraft.manufacturer,models.LogisticsAircraft.model).all()


class FleetSelectionIn(BaseModel):
    aircraft_ids: list[str] = Field(min_length=1, max_length=500)


@router.post('/companies/{company_id}/air-logistics/fleet', response_model=list[AircraftOut])
def add_to_fleet(company_id: str, payload: FleetSelectionIn, db: Session = Depends(get_db)):
    ids = set(payload.aircraft_ids)
    aircraft = db.query(models.LogisticsAircraft).filter(models.LogisticsAircraft.company_id==aircraft_company_id(db,company_id),models.LogisticsAircraft.id.in_(ids)).all()
    if len(aircraft) != len(ids):
        raise HTTPException(422,'Select existing aircraft from this aircraft database.')
    for item in aircraft:
        item.in_fleet = True
    db.flush()
    add_majestic_providers(db)
    db.commit()
    return list_aircraft(company_id,db)


@router.delete('/companies/{company_id}/air-logistics/fleet/{aircraft_id}', status_code=204)
def remove_from_fleet(company_id: str, aircraft_id: str, db: Session = Depends(get_db)):
    aircraft = db.query(models.LogisticsAircraft).filter_by(id=aircraft_id,company_id=aircraft_company_id(db,company_id)).first()
    if not aircraft:
        raise HTTPException(404,'Aircraft not found')
    if db.query(models.CharterProvider).filter_by(aircraft_id=aircraft_id).first():
        raise HTTPException(409,'This aircraft is assigned to a charter provider. Change that assignment before removing it from the fleet.')
    aircraft.in_fleet = False
    db.commit()


@router.post('/companies/{company_id}/air-logistics/aircraft', response_model=AircraftOut)
def create_aircraft(company_id: str, payload: AircraftIn, db: Session = Depends(get_db)):
    aircraft = models.LogisticsAircraft(id=str(uuid.uuid4()), company_id=aircraft_company_id(db, company_id), in_fleet=not uses_fleet_selection(db,company_id), created_at=_now(), **_clean_aircraft(payload))
    db.add(aircraft)
    db.commit()
    db.refresh(aircraft)
    return aircraft


@router.put('/companies/{company_id}/air-logistics/aircraft/{aircraft_id}', response_model=AircraftOut)
def update_aircraft(company_id: str, aircraft_id: str, payload: AircraftIn, db: Session = Depends(get_db)):
    aircraft = db.query(models.LogisticsAircraft).filter_by(id=aircraft_id, company_id=aircraft_company_id(db, company_id)).first()
    if not aircraft:
        raise HTTPException(status_code=404, detail='Aircraft not found')
    for field, value in _clean_aircraft(payload).items():
        setattr(aircraft, field, value)
    db.commit()
    db.refresh(aircraft)
    return aircraft


@router.delete('/companies/{company_id}/air-logistics/aircraft/{aircraft_id}', status_code=204)
def delete_aircraft(company_id: str, aircraft_id: str, db: Session = Depends(get_db)):
    aircraft = db.query(models.LogisticsAircraft).filter_by(id=aircraft_id, company_id=aircraft_company_id(db, company_id)).first()
    if not aircraft:
        raise HTTPException(status_code=404, detail='Aircraft not found')
    in_use = db.query(models.CharterProvider).filter_by(aircraft_id=aircraft_id).count()
    if in_use:
        raise HTTPException(status_code=400, detail=f'This aircraft is used by {in_use} charter provider(s) — change or delete them first.')
    db.delete(aircraft)
    db.commit()


@router.get('/companies/{company_id}/air-logistics/charter-providers', response_model=list[CharterProviderOut])
def list_charter_providers(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.CharterProvider).filter_by(company_id=company_id).order_by(models.CharterProvider.name).all()


@router.post('/companies/{company_id}/air-logistics/charter-providers', response_model=CharterProviderOut)
def create_charter_provider(company_id: str, payload: CharterProviderIn, db: Session = Depends(get_db)):
    provider = models.CharterProvider(
        id=str(uuid.uuid4()), company_id=company_id, created_at=_now(), **_clean_provider(db, company_id, payload)
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@router.put('/companies/{company_id}/air-logistics/charter-providers/{provider_id}', response_model=CharterProviderOut)
def update_charter_provider(company_id: str, provider_id: str, payload: CharterProviderIn, db: Session = Depends(get_db)):
    provider = db.query(models.CharterProvider).filter_by(id=provider_id, company_id=company_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail='Charter provider not found')
    for field, value in _clean_provider(db, company_id, payload,allow_incomplete=bool(provider.source_company_id)).items():
        setattr(provider, field, value)
    db.commit()
    db.refresh(provider)
    return provider


@router.delete('/companies/{company_id}/air-logistics/charter-providers/{provider_id}', status_code=204)
def delete_charter_provider(company_id: str, provider_id: str, db: Session = Depends(get_db)):
    provider = db.query(models.CharterProvider).filter_by(id=provider_id, company_id=company_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail='Charter provider not found')
    db.delete(provider)
    db.commit()
