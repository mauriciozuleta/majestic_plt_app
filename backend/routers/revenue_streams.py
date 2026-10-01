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


class RevenueStreamRouteOut(RevenueStreamRouteCreate):
    id: str
    stream_id: str
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


@router.post('/companies/{company_id}/revenue-streams/{stream_id}/routes', response_model=RevenueStreamRouteOut)
def create_revenue_stream_route(company_id: str, stream_id: str, payload: RevenueStreamRouteCreate, db: Session = Depends(get_db)):
    if not db.query(models.RevenueStream).filter_by(id=stream_id, company_id=company_id).first():
        raise HTTPException(status_code=404, detail='Revenue stream not found')
    branch_ids = {payload.origin_branch_id, payload.destination_branch_id}
    if len(branch_ids) != 2:
        raise HTTPException(status_code=400, detail='Origin and destination must be different branches.')
    found = db.query(models.CommercialBranch.id).filter(models.CommercialBranch.id.in_(branch_ids)).count()
    if found != 2:
        raise HTTPException(status_code=400, detail='Origin and destination must both be branches in the commercial structure.')
    route = models.RevenueStreamRoute(
        id=str(uuid.uuid4()),
        stream_id=stream_id,
        origin_branch_id=payload.origin_branch_id,
        destination_branch_id=payload.destination_branch_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route
