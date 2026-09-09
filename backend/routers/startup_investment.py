"""
The one-time pre-operational start-up investment plan: how many months of
runway before operations begin, and the individual line-item records (each
optionally spread across installments) that make up the cash required
across five fixed categories over that period. One plan per company.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas
from ..gl_engine import sync_opening_balance

router = APIRouter()

CATEGORIES = [
    'assets_acquisition',
    'other_assets_purchases',
    'startup_expenses',
    'startup_payroll',
    'working_capital',
]

AMOUNT_TOLERANCE = 0.01


def _get_plan_or_404(db: Session, company_id: str):
    plan = db.query(models.StartupInvestmentPlan).filter_by(company_id=company_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail='No start-up investment plan yet')
    return plan


def _record_out(record: models.StartupInvestmentRecord) -> schemas.StartupInvestmentRecordOut:
    return schemas.StartupInvestmentRecordOut(
        id=record.id,
        company_id=record.company_id,
        category=record.category,
        name=record.name,
        description=record.description,
        total_amount=record.total_amount,
        use_installments=record.use_installments,
        months=json.loads(record.months_json),
        attachment_name=record.attachment_name,
    )


def _resize_all_records(db: Session, company_id: str, new_month_count: int):
    records = db.query(models.StartupInvestmentRecord).filter_by(company_id=company_id).all()
    for record in records:
        months = json.loads(record.months_json)
        if new_month_count > len(months):
            months = months + [0.0] * (new_month_count - len(months))
        else:
            months = months[:new_month_count]
        record.months_json = json.dumps(months)


@router.get('/companies/{company_id}/startup-investment/plan', response_model=schemas.StartupInvestmentPlanOut)
def get_plan(company_id: str, db: Session = Depends(get_db)):
    return _get_plan_or_404(db, company_id)


@router.post('/companies/{company_id}/startup-investment/plan', response_model=schemas.StartupInvestmentPlanOut)
def create_plan(company_id: str, payload: schemas.StartupInvestmentPlanCreate, db: Session = Depends(get_db)):
    existing = db.query(models.StartupInvestmentPlan).filter_by(company_id=company_id).first()
    if existing:
        raise HTTPException(status_code=400, detail='A start-up investment plan already exists for this company')
    if not 1 <= payload.pre_operational_months <= 36:
        raise HTTPException(status_code=400, detail='Pre-operational months must be between 1 and 36')

    plan = models.StartupInvestmentPlan(
        id=str(uuid.uuid4()),
        company_id=company_id,
        pre_operational_months=payload.pre_operational_months,
    )
    db.add(plan)
    db.commit()
    return plan


@router.put('/companies/{company_id}/startup-investment/plan', response_model=schemas.StartupInvestmentPlanOut)
def update_plan(company_id: str, payload: schemas.StartupInvestmentPlanUpdate, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, company_id)
    if not 1 <= payload.pre_operational_months <= 36:
        raise HTTPException(status_code=400, detail='Pre-operational months must be between 1 and 36')

    plan.pre_operational_months = payload.pre_operational_months
    _resize_all_records(db, company_id, payload.pre_operational_months)
    db.commit()
    sync_opening_balance(db, company_id)
    return plan


@router.get('/companies/{company_id}/startup-investment/records', response_model=list[schemas.StartupInvestmentRecordOut])
def list_records(company_id: str, db: Session = Depends(get_db)):
    _get_plan_or_404(db, company_id)
    records = db.query(models.StartupInvestmentRecord).filter_by(company_id=company_id).all()
    order = {category: index for index, category in enumerate(CATEGORIES)}
    records.sort(key=lambda record: (order.get(record.category, len(CATEGORIES)),))
    return [_record_out(record) for record in records]


def _validate_record_payload(payload: schemas.StartupInvestmentRecordCreate, month_count: int) -> list[float]:
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail='Unknown start-up investment category')
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail='Name is required')
    if payload.total_amount <= 0:
        raise HTTPException(status_code=400, detail='Total amount must be greater than 0')

    if payload.use_installments:
        months = payload.months or []
        if len(months) != month_count:
            raise HTTPException(status_code=400, detail=f'Expected exactly {month_count} installment values')
        if abs(sum(months) - payload.total_amount) > AMOUNT_TOLERANCE:
            raise HTTPException(status_code=400, detail='Installments must add up to the total amount')
        return months
    return [payload.total_amount] + [0.0] * (month_count - 1)


@router.post('/companies/{company_id}/startup-investment/records', response_model=schemas.StartupInvestmentRecordOut)
def create_record(company_id: str, payload: schemas.StartupInvestmentRecordCreate, db: Session = Depends(get_db)):
    plan = _get_plan_or_404(db, company_id)
    months = _validate_record_payload(payload, plan.pre_operational_months)

    record = models.StartupInvestmentRecord(
        id=str(uuid.uuid4()),
        company_id=company_id,
        category=payload.category,
        name=payload.name.strip(),
        description=payload.description,
        total_amount=payload.total_amount,
        use_installments=payload.use_installments,
        months_json=json.dumps(months),
    )
    db.add(record)
    db.commit()
    sync_opening_balance(db, company_id)
    return _record_out(record)


@router.put(
    '/companies/{company_id}/startup-investment/records/{record_id}',
    response_model=schemas.StartupInvestmentRecordOut,
)
def update_record(
    company_id: str,
    record_id: str,
    payload: schemas.StartupInvestmentRecordCreate,
    db: Session = Depends(get_db),
):
    plan = _get_plan_or_404(db, company_id)
    record = db.query(models.StartupInvestmentRecord).filter_by(id=record_id, company_id=company_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Record not found')

    months = _validate_record_payload(payload, plan.pre_operational_months)

    record.category = payload.category
    record.name = payload.name.strip()
    record.description = payload.description
    record.total_amount = payload.total_amount
    record.use_installments = payload.use_installments
    record.months_json = json.dumps(months)
    db.commit()
    sync_opening_balance(db, company_id)
    return _record_out(record)


@router.delete('/companies/{company_id}/startup-investment/records/{record_id}')
def delete_record(company_id: str, record_id: str, db: Session = Depends(get_db)):
    record = db.query(models.StartupInvestmentRecord).filter_by(id=record_id, company_id=company_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Record not found')
    db.delete(record)
    db.commit()
    sync_opening_balance(db, company_id)
    return {'ok': True}
