"""Providers per expense category (COS/Expenses ▸ Providers ▸ Expenses, and
the Provider dropdown in Commercial Operations' Add Expense form).

The list is the union of providers added by hand (models.ExpenseProvider)
and every provider already named on a saved expense — an expenses entry's
`description` is its category and `paid_to` its provider — de-duplicated
case-insensitively, so recording an expense adds its provider automatically."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter()


class ExpenseProviderIn(BaseModel):
    category_name: str
    name: str


def _norm(value: str) -> str:
    return ' '.join((value or '').split()).lower()


@router.get('/companies/{company_id}/expense-providers')
def list_expense_providers(company_id: str, db: Session = Depends(get_db)):
    """[{category, providers: [{name, source: 'manual' | 'expense', expense_count}]}],
    categories and providers sorted by name."""
    categories: dict[str, dict] = {}

    def add(category: str, name: str, source: str):
        category, name = ' '.join(category.split()), ' '.join(name.split())
        if not category or not name:
            return
        bucket = categories.setdefault(_norm(category), {'category': category, 'providers': {}})
        provider = bucket['providers'].setdefault(_norm(name), {'name': name, 'source': source, 'expense_count': 0})
        if source == 'expense':
            provider['expense_count'] += 1

    for row in db.query(models.ExpenseProvider).filter_by(company_id=company_id):
        add(row.category_name, row.name, 'manual')
    entries = db.query(models.CommercialOperationEntry.description, models.CommercialOperationEntry.paid_to).filter_by(
        company_id=company_id, category='expenses'
    )
    for category, paid_to in entries:
        add(category or '', paid_to or '', 'expense')

    return [
        {'category': bucket['category'], 'providers': sorted(bucket['providers'].values(), key=lambda p: p['name'].lower())}
        for bucket in sorted(categories.values(), key=lambda b: b['category'].lower())
    ]


@router.post('/companies/{company_id}/expense-providers')
def create_expense_provider(company_id: str, payload: ExpenseProviderIn, db: Session = Depends(get_db)):
    category = ' '.join(payload.category_name.split())
    name = ' '.join(payload.name.split())
    if not category:
        raise HTTPException(status_code=400, detail='Choose an expense category.')
    if not name:
        raise HTTPException(status_code=400, detail='Enter the provider name.')
    existing = [
        row
        for row in db.query(models.ExpenseProvider).filter_by(company_id=company_id)
        if _norm(row.category_name) == _norm(category) and _norm(row.name) == _norm(name)
    ]
    if existing:
        raise HTTPException(status_code=409, detail=f'"{name}" is already a provider for {category}.')
    row = models.ExpenseProvider(
        id=str(uuid.uuid4()), company_id=company_id, category_name=category, name=name, created_at=datetime.now(timezone.utc).isoformat()
    )
    db.add(row)
    db.commit()
    return {'id': row.id, 'category_name': row.category_name, 'name': row.name}
