import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()

VALID_REVENUE_TYPES = {'main', 'secondary'}


class RevenueStreamCreate(BaseModel):
    revenue_type: str
    name: str


class RevenueStreamOut(RevenueStreamCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


@router.get('/companies/{company_id}/revenue-streams', response_model=list[RevenueStreamOut])
def list_revenue_streams(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.RevenueStream).filter_by(company_id=company_id).all()


@router.post('/companies/{company_id}/revenue-streams', response_model=RevenueStreamOut)
def create_revenue_stream(company_id: str, payload: RevenueStreamCreate, db: Session = Depends(get_db)):
    if payload.revenue_type not in VALID_REVENUE_TYPES:
        raise HTTPException(status_code=400, detail='revenue_type must be one of: main, secondary')
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail='name is required')

    stream = models.RevenueStream(
        id=str(uuid.uuid4()),
        company_id=company_id,
        revenue_type=payload.revenue_type,
        name=payload.name.strip(),
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


class RevenueStreamRouteCreate(BaseModel):
    origin_branch_id: str
    destination_branch_id: str
    return_branch_id: str
    charter_provider_id: str
    aircraft_id: str


# Set from the route's expanded card, not the route form. Only the fields
# sent are changed; null clears one.
class RevenueStreamRouteSettings(BaseModel):
    return_type: str | None = None
    outbound_target_cargo_pct: float | None = None
    return_target_cargo_pct: float | None = None
    return_price_per_kg: float | None = None
    outbound_leg_cost_pct: float | None = None
    return_leg_cost_pct: float | None = None


RETURN_TYPES = {'full', 'compensated'}


class RevenueStreamRouteOut(BaseModel):
    id: str
    stream_id: str
    origin_branch_id: str
    destination_branch_id: str
    return_branch_id: str | None = None
    charter_provider_id: str | None = None
    aircraft_id: str | None = None
    provider_name: str | None = None
    aircraft_name: str | None = None
    return_type: str | None = None
    outbound_target_cargo_pct: float | None = None
    return_target_cargo_pct: float | None = None
    return_price_per_kg: float | None = None
    outbound_leg_cost_pct: float | None = None
    return_leg_cost_pct: float | None = None
    created_at: str

    class Config:
        from_attributes = True


@router.get('/companies/{company_id}/revenue-streams/routes', response_model=list[RevenueStreamRouteOut])
def list_revenue_stream_routes(company_id: str, db: Session = Depends(get_db)):
    """Every route on every one of this company's revenue streams, oldest first."""
    stream_ids = [stream.id for stream in db.query(models.RevenueStream).filter_by(company_id=company_id)]
    return (
        db.query(models.RevenueStreamRoute)
        .filter(models.RevenueStreamRoute.stream_id.in_(stream_ids))
        .order_by(models.RevenueStreamRoute.created_at)
        .all()
    )


def _validated_route_fields(db: Session, company_id: str, payload: RevenueStreamRouteCreate) -> dict:
    """Checks the two branches and the provider/aircraft pair, and returns the
    column values to store (including the provider/aircraft display names)."""
    if payload.origin_branch_id == payload.destination_branch_id:
        raise HTTPException(status_code=400, detail='Origin and destination must be different branches.')
    if payload.return_branch_id == payload.destination_branch_id:
        raise HTTPException(status_code=400, detail='The return airport must differ from the destination.')
    # The return airport may be the origin itself (a round trip).
    branch_ids = {payload.origin_branch_id, payload.destination_branch_id, payload.return_branch_id}
    found = db.query(models.CommercialBranch.id).filter(models.CommercialBranch.id.in_(branch_ids)).count()
    if found != len(branch_ids):
        raise HTTPException(status_code=400, detail='Origin, destination and return must all be branches in the commercial structure.')
    provider = db.query(models.CharterProvider).filter_by(id=payload.charter_provider_id, company_id=company_id).first()
    if not provider:
        raise HTTPException(status_code=400, detail='Choose an air logistics provider from Providers ▸ Air Logistics.')
    # A provider record flies exactly one aircraft; a provider with several
    # aircraft has one record per aircraft.
    if provider.aircraft_id != payload.aircraft_id:
        raise HTTPException(status_code=400, detail='That aircraft is not assigned to this provider.')
    aircraft = db.query(models.LogisticsAircraft).filter_by(id=payload.aircraft_id).first()
    return {
        'origin_branch_id': payload.origin_branch_id,
        'destination_branch_id': payload.destination_branch_id,
        'return_branch_id': payload.return_branch_id,
        'charter_provider_id': provider.id,
        'aircraft_id': payload.aircraft_id,
        'provider_name': provider.name,
        'aircraft_name': f'{aircraft.short_name} ({aircraft.model})' if aircraft else None,
    }


def _get_route(db: Session, company_id: str, stream_id: str, route_id: str) -> models.RevenueStreamRoute:
    if not db.query(models.RevenueStream).filter_by(id=stream_id, company_id=company_id).first():
        raise HTTPException(status_code=404, detail='Revenue stream not found')
    route = db.query(models.RevenueStreamRoute).filter_by(id=route_id, stream_id=stream_id).first()
    if not route:
        raise HTTPException(status_code=404, detail='Route not found')
    return route


@router.post('/companies/{company_id}/revenue-streams/{stream_id}/routes', response_model=RevenueStreamRouteOut)
def create_revenue_stream_route(company_id: str, stream_id: str, payload: RevenueStreamRouteCreate, db: Session = Depends(get_db)):
    if not db.query(models.RevenueStream).filter_by(id=stream_id, company_id=company_id).first():
        raise HTTPException(status_code=404, detail='Revenue stream not found')
    route = models.RevenueStreamRoute(
        id=str(uuid.uuid4()),
        stream_id=stream_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        **_validated_route_fields(db, company_id, payload),
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.put('/companies/{company_id}/revenue-streams/{stream_id}/routes/{route_id}', response_model=RevenueStreamRouteOut)
def update_revenue_stream_route(
    company_id: str, stream_id: str, route_id: str, payload: RevenueStreamRouteCreate, db: Session = Depends(get_db)
):
    route = _get_route(db, company_id, stream_id, route_id)
    for field, value in _validated_route_fields(db, company_id, payload).items():
        setattr(route, field, value)
    db.commit()
    db.refresh(route)
    return route


@router.patch('/companies/{company_id}/revenue-streams/{stream_id}/routes/{route_id}/settings', response_model=RevenueStreamRouteOut)
def update_revenue_stream_route_settings(
    company_id: str, stream_id: str, route_id: str, payload: RevenueStreamRouteSettings, db: Session = Depends(get_db)
):
    changes = payload.model_dump(include=payload.model_fields_set)
    if changes.get('return_type') is not None and changes['return_type'] not in RETURN_TYPES:
        raise HTTPException(status_code=400, detail="Type of return must be 'full' or 'compensated'.")
    for field in ('outbound_target_cargo_pct', 'return_target_cargo_pct', 'outbound_leg_cost_pct', 'return_leg_cost_pct'):
        value = changes.get(field)
        if value is not None and not 0 <= value <= 100:
            raise HTTPException(status_code=400, detail='Percentages must be between 0 and 100.')
    if changes.get('return_price_per_kg') is not None and changes['return_price_per_kg'] < 0:
        raise HTTPException(status_code=400, detail='Price per kg cannot be negative.')
    route = _get_route(db, company_id, stream_id, route_id)
    for field, value in changes.items():
        setattr(route, field, value)
    db.commit()
    db.refresh(route)
    return route


@router.delete('/companies/{company_id}/revenue-streams/{stream_id}/routes/{route_id}', status_code=204)
def delete_revenue_stream_route(company_id: str, stream_id: str, route_id: str, db: Session = Depends(get_db)):
    route = _get_route(db, company_id, stream_id, route_id)
    db.delete(route)
    db.commit()
