"""Per-company Payroll Schedule settings: which bank account each payroll
disbursement category (Payroll / Taxes & Contributions / Benefits) debits,
and whether the schedule auto-generates its Commercial Operations entries.
Separate from PortfolioSettings' (portfolio-wide) payroll-schedule-type/day
fields because bank accounts are per-company."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()


def _get_or_create(db: Session, company_id: str) -> models.PayrollScheduleSettings:
    row = db.query(models.PayrollScheduleSettings).filter_by(company_id=company_id).first()
    if not row:
        row = models.PayrollScheduleSettings(company_id=company_id, automatic_schedule=False)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _serialize(row: models.PayrollScheduleSettings) -> dict:
    return {
        'payroll_bank_account_id': row.payroll_bank_account_id,
        'taxes_bank_account_id': row.taxes_bank_account_id,
        'benefits_bank_account_id': row.benefits_bank_account_id,
        'automatic_schedule': bool(row.automatic_schedule),
    }


@router.get('/companies/{company_id}/payroll-schedule-settings')
def get_payroll_schedule_settings(company_id: str, db: Session = Depends(get_db)):
    return _serialize(_get_or_create(db, company_id))


@router.patch('/companies/{company_id}/payroll-schedule-settings')
def update_payroll_schedule_settings(company_id: str, payload: dict, db: Session = Depends(get_db)):
    row = _get_or_create(db, company_id)

    if 'payroll_bank_account_id' in payload:
        row.payroll_bank_account_id = payload.get('payroll_bank_account_id') or None
    if 'taxes_bank_account_id' in payload:
        row.taxes_bank_account_id = payload.get('taxes_bank_account_id') or None
    if 'benefits_bank_account_id' in payload:
        row.benefits_bank_account_id = payload.get('benefits_bank_account_id') or None
    if 'automatic_schedule' in payload:
        row.automatic_schedule = bool(payload.get('automatic_schedule'))

    db.commit()
    return _serialize(row)
