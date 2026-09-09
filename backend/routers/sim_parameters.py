"""
Link table flagging which commercial-operations entries are candidate
"simulation parameters" — values a future simulation agent should be able to
manipulate. This router only records the flag; no simulation logic reads it
yet.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()


class SimParameterCreate(BaseModel):
    entry_id: str


class SimParameterOut(BaseModel):
    id: str
    company_id: str
    entry_id: str

    class Config:
        from_attributes = True


@router.get('/companies/{company_id}/sim-parameters', response_model=list[SimParameterOut])
def list_sim_parameters(company_id: str, db: Session = Depends(get_db)):
    return db.query(models.SimParameter).filter_by(company_id=company_id).all()


@router.post('/companies/{company_id}/sim-parameters', response_model=SimParameterOut)
def create_sim_parameter(company_id: str, payload: SimParameterCreate, db: Session = Depends(get_db)):
    entry = db.query(models.CommercialOperationEntry).filter_by(id=payload.entry_id, company_id=company_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Entry not found')

    existing = db.query(models.SimParameter).filter_by(entry_id=payload.entry_id).first()
    if existing:
        return existing

    sim_parameter = models.SimParameter(id=str(uuid.uuid4()), company_id=company_id, entry_id=payload.entry_id)
    db.add(sim_parameter)
    db.commit()
    db.refresh(sim_parameter)
    return sim_parameter


@router.delete('/companies/{company_id}/sim-parameters/{entry_id}')
def delete_sim_parameter(company_id: str, entry_id: str, db: Session = Depends(get_db)):
    sim_parameter = db.query(models.SimParameter).filter_by(company_id=company_id, entry_id=entry_id).first()
    if not sim_parameter:
        raise HTTPException(status_code=404, detail='Sim parameter not found')
    db.delete(sim_parameter)
    db.commit()
    return {'ok': True}
