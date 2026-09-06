"""
Per-company revenue / cost-of-sales / expenses entries plotted on the
Commercial Operations calendar. Dates are stored as plain ISO strings, same
convention as every other date field in this app (Roadmap tasks, Payroll
employees) — simulation-mode interpretation happens client-side, not here.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()

VALID_CATEGORIES = {'revenue', 'cos', 'expenses'}


@router.get('/companies/{company_id}/commercial-operations', response_model=list[schemas.CommercialOperationEntryOut])
def list_commercial_operation_entries(company_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.CommercialOperationEntry)
        .filter_by(company_id=company_id)
        .order_by(models.CommercialOperationEntry.entry_date)
        .all()
    )


@router.post('/companies/{company_id}/commercial-operations', response_model=schemas.CommercialOperationEntryOut)
def create_commercial_operation_entry(
    company_id: str,
    payload: schemas.CommercialOperationEntryCreate,
    db: Session = Depends(get_db),
):
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail='category must be one of: revenue, cos, expenses')

    entry = models.CommercialOperationEntry(
        id=str(uuid.uuid4()),
        company_id=company_id,
        category=payload.category,
        entry_date=payload.entry_date,
        description=payload.description,
        amount=payload.amount,
    )
    db.add(entry)
    db.commit()
    return entry


@router.delete('/companies/{company_id}/commercial-operations/{entry_id}')
def delete_commercial_operation_entry(company_id: str, entry_id: str, db: Session = Depends(get_db)):
    entry = db.query(models.CommercialOperationEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Entry not found')
    db.delete(entry)
    db.commit()
    return {'ok': True}
