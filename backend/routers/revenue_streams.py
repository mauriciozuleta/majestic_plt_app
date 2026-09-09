import uuid

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
