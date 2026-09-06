"""
The one-time pre-operational start-up investment plan: how many months of
runway before operations begin, and the cash required across five fixed
categories over that period. One plan per company.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()

CATEGORIES = [
    'assets_acquisition',
    'other_assets_purchases',
    'startup_expenses',
    'startup_payroll',
    'working_capital',
]


def _get_plan_or_404(db: Session, company_id: str):
    plan = db.query(models.StartupInvestmentPlan).filter_by(company_id=company_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail='No start-up investment plan yet')
    return plan


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

    zeros = json.dumps([0.0] * payload.pre_operational_months)
    for category in CATEGORIES:
        db.add(
            models.StartupInvestmentEntry(
                id=str(uuid.uuid4()),
                company_id=company_id,
                category=category,
                months_json=zeros,
            )
        )

    db.commit()
    return plan


@router.get('/companies/{company_id}/startup-investment/entries', response_model=list[schemas.StartupInvestmentEntryOut])
def list_entries(company_id: str, db: Session = Depends(get_db)):
    _get_plan_or_404(db, company_id)
    entries = db.query(models.StartupInvestmentEntry).filter_by(company_id=company_id).all()
    order = {category: index for index, category in enumerate(CATEGORIES)}
    entries.sort(key=lambda entry: order.get(entry.category, len(CATEGORIES)))
    return [
        schemas.StartupInvestmentEntryOut(category=entry.category, months=json.loads(entry.months_json))
        for entry in entries
    ]


@router.put(
    '/companies/{company_id}/startup-investment/entries/{category}',
    response_model=schemas.StartupInvestmentEntryOut,
)
def update_entry(
    company_id: str,
    category: str,
    payload: schemas.StartupInvestmentEntryUpdate,
    db: Session = Depends(get_db),
):
    plan = _get_plan_or_404(db, company_id)
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail='Unknown start-up investment category')
    if len(payload.months) != plan.pre_operational_months:
        raise HTTPException(status_code=400, detail=f'Expected exactly {plan.pre_operational_months} month values')

    entry = db.query(models.StartupInvestmentEntry).filter_by(company_id=company_id, category=category).first()
    if not entry:
        entry = models.StartupInvestmentEntry(id=str(uuid.uuid4()), company_id=company_id, category=category)
        db.add(entry)

    entry.months_json = json.dumps(payload.months)
    db.commit()
    return schemas.StartupInvestmentEntryOut(category=category, months=payload.months)
