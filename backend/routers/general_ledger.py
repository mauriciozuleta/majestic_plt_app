from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..gl_engine import ensure_default_accounts

router = APIRouter()


class AccountOut(BaseModel):
    id: str
    code: str
    name: str
    account_type: str
    normal_balance: str

    class Config:
        from_attributes = True


class JournalLineOut(BaseModel):
    id: str
    account_id: str
    account_code: str
    account_name: str
    debit: float
    credit: float


class JournalEntryOut(BaseModel):
    id: str
    entry_date: str
    memo: str | None
    source_type: str | None
    source_id: str | None
    lines: list[JournalLineOut]


@router.get('/companies/{company_id}/gl/accounts', response_model=list[AccountOut])
def list_accounts(company_id: str, db: Session = Depends(get_db)):
    ensure_default_accounts(db, company_id)
    return (
        db.query(models.GeneralLedgerAccount)
        .filter_by(company_id=company_id)
        .order_by(models.GeneralLedgerAccount.code)
        .all()
    )


@router.get('/companies/{company_id}/gl/journal-entries', response_model=list[JournalEntryOut])
def list_journal_entries(company_id: str, db: Session = Depends(get_db)):
    accounts = {
        account.id: account
        for account in db.query(models.GeneralLedgerAccount).filter_by(company_id=company_id).all()
    }

    entries = (
        db.query(models.JournalEntry)
        .filter_by(company_id=company_id)
        .order_by(models.JournalEntry.entry_date, models.JournalEntry.id)
        .all()
    )
    entry_ids = [entry.id for entry in entries]
    lines = (
        db.query(models.JournalLine).filter(models.JournalLine.journal_entry_id.in_(entry_ids)).all()
        if entry_ids
        else []
    )
    lines_by_entry = {}
    for line in lines:
        lines_by_entry.setdefault(line.journal_entry_id, []).append(line)

    result = []
    for entry in entries:
        entry_lines = []
        for line in lines_by_entry.get(entry.id, []):
            account = accounts.get(line.account_id)
            entry_lines.append(
                JournalLineOut(
                    id=line.id,
                    account_id=line.account_id,
                    account_code=account.code if account else '?',
                    account_name=account.name if account else 'Unknown account',
                    debit=line.debit,
                    credit=line.credit,
                )
            )
        result.append(
            JournalEntryOut(
                id=entry.id,
                entry_date=entry.entry_date,
                memo=entry.memo,
                source_type=entry.source_type,
                source_id=entry.source_id,
                lines=entry_lines,
            )
        )
    return result
