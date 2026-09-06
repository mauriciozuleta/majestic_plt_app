"""
The portfolio-wide payroll grade table (C1, C2, ... F4 and their yearly/
monthly comp) — edited from Settings, and used in the Payroll Matrix to
drive each position's "Level" dropdown. Global across all companies, not
scoped to one, so there's a single flat list rather than a company_id.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()


@router.get('/payroll-levels', response_model=list[schemas.PayrollLevelOut])
def list_payroll_levels(db: Session = Depends(get_db)):
    return db.query(models.PayrollLevel).order_by(models.PayrollLevel.sort_order).all()


@router.put('/payroll-levels', response_model=list[schemas.PayrollLevelOut])
def replace_payroll_levels(payload: list[schemas.PayrollLevelIn], db: Session = Depends(get_db)):
    db.query(models.PayrollLevel).delete()
    for index, item in enumerate(payload):
        db.add(
            models.PayrollLevel(
                id=str(uuid.uuid4()),
                sort_order=index,
                level=item.level,
                yearly=item.yearly,
                percentage=item.percentage,
                monthly=item.monthly,
            )
        )
    db.commit()
    return db.query(models.PayrollLevel).order_by(models.PayrollLevel.sort_order).all()
