"""Bank Accounts — a per-company list of bank accounts (name, account
number, Main/Secondary type, display name, logo). This is a first pass:
just the record itself, no transactions/reconciliation yet — that's a
later module."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..gl_engine import sync_opening_balance

router = APIRouter()

ACCOUNT_TYPES = {'main', 'secondary'}
INTERNAL_TRANSFER_LABEL = 'Internal Cash Transfer'


class BankAccountCreate(BaseModel):
    bank_name: str
    account_number: str
    account_type: str
    account_name: str
    logo: str | None = None
    is_reserve: bool = False


class BankAccountOut(BankAccountCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class BankTransactionOut(BaseModel):
    id: str
    bank_account_id: str
    entry_date: str
    description: str | None = None
    client: str | None = None
    reference: str | None = None
    credit: float
    debit: float
    # Lets the frontend tell a real cos/expense transaction apart from an
    # internal transfer or reserve-funding leg — needed to compute the
    # "committed vs free" breakdown (see BankLedgerPanel.jsx), which only
    # ever counts commercial_operation_entry rows.
    source_type: str | None = None
    # Shared by a reserve-funded entry's funding-transfer leg and its
    # eventual disbursement leg (both point back at the same
    # CommercialOperationEntry.id) — lets the frontend pair them up so a
    # pending disbursement is only ever flagged "committed" once its own
    # funding has actually landed in the account, not before.
    source_id: str | None = None

    class Config:
        from_attributes = True


class BankTransferCreate(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: float
    entry_date: str


@router.get('/companies/{company_id}/bank-accounts', response_model=list[BankAccountOut])
def list_bank_accounts(company_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.BankAccount)
        .filter_by(company_id=company_id)
        .order_by(models.BankAccount.bank_name, models.BankAccount.account_type)
        .all()
    )


@router.post('/companies/{company_id}/bank-accounts', response_model=BankAccountOut)
def create_bank_account(company_id: str, payload: BankAccountCreate, db: Session = Depends(get_db)):
    bank_name = payload.bank_name.strip()
    if not bank_name:
        raise HTTPException(status_code=400, detail='Bank name is required.')

    account_number = payload.account_number.strip()
    if not account_number:
        raise HTTPException(status_code=400, detail='Account number is required.')

    account_type = payload.account_type.strip().lower()
    if account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="account_type must be 'main' or 'secondary'")

    account_name = payload.account_name.strip()
    if not account_name:
        raise HTTPException(status_code=400, detail='Account name is required.')

    if account_type == 'main':
        # bank_name is free-typed, so match case/whitespace-insensitively —
        # otherwise "Bank of America" and "bank of  america" would count as
        # different banks and this check would never catch a real duplicate.
        normalized_bank_name = ' '.join(bank_name.split()).lower()
        existing_main = next(
            (
                account
                for account in db.query(models.BankAccount).filter_by(company_id=company_id, account_type='main').all()
                if ' '.join(account.bank_name.split()).lower() == normalized_bank_name
            ),
            None,
        )
        if existing_main:
            raise HTTPException(
                status_code=400,
                detail=f'"{bank_name}" already has a Main account for this company — only one is allowed per bank.',
            )

    account = models.BankAccount(
        id=str(uuid.uuid4()),
        company_id=company_id,
        bank_name=bank_name,
        account_number=account_number,
        account_type=account_type,
        account_name=account_name,
        logo=payload.logo or None,
        is_reserve=payload.is_reserve,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    if account_type == 'main':
        # Attaches this account's opening-balance transaction (the company's
        # Total Start-up Working Capital, if any) immediately — otherwise it
        # would sit unattached until the next Start-up Investment edit
        # happened to re-run this sync.
        sync_opening_balance(db, company_id)

    return account


@router.delete('/bank-accounts/{account_id}')
def delete_bank_account(account_id: str, db: Session = Depends(get_db)):
    account = db.query(models.BankAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail='Bank account not found')
    if account.account_type == 'main':
        raise HTTPException(
            status_code=400,
            detail='A company must have a Main bank account to be able to operate — this account cannot be deleted.',
        )
    db.delete(account)
    db.commit()
    return {'ok': True}


@router.get('/bank-accounts/{account_id}/transactions', response_model=list[BankTransactionOut])
def list_bank_transactions(account_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.BankTransaction)
        .filter_by(bank_account_id=account_id)
        .order_by(models.BankTransaction.entry_date, models.BankTransaction.created_at)
        .all()
    )


@router.post('/bank-accounts/transfer')
def create_bank_transfer(payload: BankTransferCreate, db: Session = Depends(get_db)):
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(status_code=400, detail='Choose two different accounts.')
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail='Amount must be greater than 0.')

    from_account = db.query(models.BankAccount).filter_by(id=payload.from_account_id).first()
    if not from_account:
        raise HTTPException(status_code=404, detail='Origin account not found')
    to_account = db.query(models.BankAccount).filter_by(id=payload.to_account_id).first()
    if not to_account:
        raise HTTPException(status_code=404, detail='Destination account not found')

    transfer_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    db.add(
        models.BankTransaction(
            id=str(uuid.uuid4()),
            bank_account_id=from_account.id,
            entry_date=payload.entry_date,
            description=f'Transfer to {to_account.account_name}',
            client=INTERNAL_TRANSFER_LABEL,
            credit=0.0,
            debit=payload.amount,
            source_type='internal_transfer',
            source_id=transfer_id,
            created_at=now,
        )
    )
    db.add(
        models.BankTransaction(
            id=str(uuid.uuid4()),
            bank_account_id=to_account.id,
            entry_date=payload.entry_date,
            description=f'Transfer from {from_account.account_name}',
            client=INTERNAL_TRANSFER_LABEL,
            credit=payload.amount,
            debit=0.0,
            source_type='internal_transfer',
            source_id=transfer_id,
            created_at=now,
        )
    )
    db.commit()
    return {'ok': True, 'transfer_id': transfer_id}
