"""
The portfolio-wide expense category list (Marketing & Advertising, Auto
Expense, ...) plus each company's per-year, per-month cost entries against
those categories. The "Payroll" category is never stored/edited here — the
frontend overlays it with the live monthly payroll cost from the Payroll
module instead, so it can never drift out of sync with actual payroll data.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()

PAYROLL_CATEGORY_NAME = 'Payroll'


@router.get('/expense-categories', response_model=list[schemas.ExpenseCategoryOut])
def list_expense_categories(db: Session = Depends(get_db)):
    return db.query(models.ExpenseCategory).order_by(models.ExpenseCategory.sort_order).all()


@router.get('/companies/{company_id}/expenses', response_model=list[schemas.ExpenseEntryOut])
def list_expenses(company_id: str, year: int = 1, db: Session = Depends(get_db)):
    categories = db.query(models.ExpenseCategory).order_by(models.ExpenseCategory.sort_order).all()
    rows = []
    for category in categories:
        entry = db.query(models.ExpenseEntry).filter_by(
            company_id=company_id, category_id=category.id, projection_year=year,
        ).first()
        months = json.loads(entry.months_json) if entry else [0.0] * 12
        hardcoded = json.loads(entry.hardcoded_json) if entry and entry.hardcoded_json else [False] * 12
        rows.append(
            schemas.ExpenseEntryOut(
                category_id=category.id,
                name=category.name,
                sort_order=category.sort_order,
                projection_year=year,
                months=months,
                hardcoded=hardcoded,
                editable=category.name != PAYROLL_CATEGORY_NAME,
            )
        )
    return rows


@router.put('/companies/{company_id}/expenses/{category_id}', response_model=schemas.ExpenseEntryOut)
def update_expense_entry(
    company_id: str,
    category_id: str,
    payload: schemas.ExpenseEntryUpdate,
    year: int = 1,
    db: Session = Depends(get_db),
):
    category = db.query(models.ExpenseCategory).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Expense category not found')
    if category.name == PAYROLL_CATEGORY_NAME:
        raise HTTPException(status_code=400, detail='Payroll costs are imported automatically and cannot be edited here.')
    if len(payload.months) != 12:
        raise HTTPException(status_code=400, detail='Expected exactly 12 month values.')
    if len(payload.hardcoded) != 12:
        raise HTTPException(status_code=400, detail='Expected exactly 12 hardcoded flags.')

    entry = db.query(models.ExpenseEntry).filter_by(
        company_id=company_id, category_id=category_id, projection_year=year,
    ).first()
    if not entry:
        entry = models.ExpenseEntry(
            id=str(uuid.uuid4()),
            company_id=company_id,
            category_id=category_id,
            projection_year=year,
        )
        db.add(entry)

    entry.months_json = json.dumps(payload.months)
    entry.hardcoded_json = json.dumps(payload.hardcoded)
    db.commit()

    return schemas.ExpenseEntryOut(
        category_id=category.id,
        name=category.name,
        sort_order=category.sort_order,
        projection_year=year,
        months=payload.months,
        hardcoded=payload.hardcoded,
        editable=True,
    )
