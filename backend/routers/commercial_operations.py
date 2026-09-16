"""
Per-company revenue / cost-of-sales / expenses entries plotted on the
Commercial Operations calendar. Dates are stored as plain ISO strings, same
convention as every other date field in this app (Roadmap tasks, Payroll
employees) — simulation-mode interpretation happens client-side, not here.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .. import schemas
from ..gl_engine import CASH_TIMING_BY_TREATMENT, expected_cash_date, post_commercial_operation_entry, unpost_commercial_operation_entry

router = APIRouter()

VALID_CATEGORIES = {'revenue', 'cos', 'expenses'}
RESERVE_TRANSFER_SOURCE_TYPE = 'commercial_operation_reserve_transfer'


def _validate_reserve_account(payload):
    if not payload.reserve_account_id:
        return
    # Reserve funding only makes sense for an obligation that isn't paid
    # until some later settlement_date (an accrued cos/expense) — there's no
    # gap between accrual and payment to hold cash aside for otherwise, and
    # revenue's own settlement-timed treatment is money coming in, not an
    # obligation to fund.
    if CASH_TIMING_BY_TREATMENT.get((payload.category, payload.accounting_treatment)) != 'settlement':
        raise HTTPException(
            status_code=400,
            detail='Internal operation (reserve funding) only applies to a treatment with a future settlement date, '
            'such as an accrued cost or expense.',
        )
    if payload.reserve_account_id == payload.bank_account_id:
        raise HTTPException(status_code=400, detail='Choose a reserve account different from the entry\'s own bank account.')


def _post_bank_transaction(db: Session, entry: models.CommercialOperationEntry):
    """Revenue entries post a credit to the chosen bank account's ledger;
    cos/expenses entries post a debit. The ledger's origin/beneficiary column
    shows who the money came from (revenue's client) or who it went to
    (cos/expenses' paid_to).

    Not every entry moves cash, and not always on entry_date — gl_engine's
    own expected_cash_date() says which leg of its postings actually touches
    the Cash account, and on which date, per (category, accounting_treatment).
    An "Inventory Consumption" entry moves Inventory to COGS with no cash
    involved at all (the cash left when the inventory was purchased, not
    now), so it gets no bank transaction; a "Deferred Revenue" entry's cash
    arrives at entry_date (the customer pays now) even though it also carries
    a settlement_date for when the service is later delivered, so it's dated
    on entry_date, not settlement_date."""
    transaction_date = expected_cash_date(entry)
    if transaction_date is None:
        return

    credit = entry.amount if entry.category == 'revenue' else 0.0
    debit = entry.amount if entry.category in ('cos', 'expenses') else 0.0
    counterparty = entry.client if entry.category == 'revenue' else entry.paid_to
    # An "internal operation" entry has its cash pre-funded into a reserve
    # account at entry_date (see below) — the real disbursement that clears
    # the liability draws from there instead of the account picked on the
    # form, or the same amount would leave the books twice.
    disbursement_account_id = entry.reserve_account_id or entry.bank_account_id
    db.add(
        models.BankTransaction(
            id=str(uuid.uuid4()),
            bank_account_id=disbursement_account_id,
            entry_date=transaction_date,
            description=entry.description or entry.entry_type or entry.client or entry.category,
            client=counterparty,
            reference=entry.reference_document,
            credit=credit,
            debit=debit,
            source_type='commercial_operation_entry',
            source_id=entry.id,
            created_at=datetime.utcnow().isoformat(),
        )
    )

    if entry.reserve_account_id:
        _post_reserve_transfer(db, entry)


def _post_reserve_transfer(db: Session, entry: models.CommercialOperationEntry):
    """Moves entry.amount out of the entry's own bank account and into its
    reserve account, dated entry_date — a pure asset-to-asset internal
    transfer (same mechanic as POST /bank-accounts/transfer), with no P&L
    effect and no journal entry. This is what actually takes the cash out of
    "general available" funds; the liability booked by
    post_commercial_operation_entry stays open until the real settlement-date
    disbursement above draws it back out of the reserve."""
    now = datetime.utcnow().isoformat()
    db.add(
        models.BankTransaction(
            id=str(uuid.uuid4()),
            bank_account_id=entry.bank_account_id,
            entry_date=entry.entry_date,
            description=f'Reserve funding: {entry.description or entry.entry_type or entry.category}',
            client='Internal Reserve Transfer',
            credit=0.0,
            debit=entry.amount,
            source_type=RESERVE_TRANSFER_SOURCE_TYPE,
            source_id=entry.id,
            created_at=now,
        )
    )
    db.add(
        models.BankTransaction(
            id=str(uuid.uuid4()),
            bank_account_id=entry.reserve_account_id,
            entry_date=entry.entry_date,
            description=f'Reserve funding: {entry.description or entry.entry_type or entry.category}',
            client='Internal Reserve Transfer',
            credit=entry.amount,
            debit=0.0,
            source_type=RESERVE_TRANSFER_SOURCE_TYPE,
            source_id=entry.id,
            created_at=now,
        )
    )


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
    if not payload.bank_account_id:
        raise HTTPException(status_code=400, detail='A bank account is required.')
    _validate_reserve_account(payload)

    entry = models.CommercialOperationEntry(
        id=str(uuid.uuid4()),
        company_id=company_id,
        category=payload.category,
        entry_date=payload.entry_date,
        description=payload.description,
        entry_type=payload.entry_type,
        client=payload.client,
        amount=payload.amount,
        accounting_treatment=payload.accounting_treatment,
        is_recurring=payload.is_recurring,
        is_discount=payload.is_discount,
        settlement_date=payload.settlement_date,
        bank_account_id=payload.bank_account_id,
        reference_document=payload.reference_document,
        paid_to=payload.paid_to,
        recurrence_frequency=payload.recurrence_frequency,
        recurrence_interval=payload.recurrence_interval,
        recurrence_custom_unit=payload.recurrence_custom_unit,
        recurrence_until_date=payload.recurrence_until_date,
        source=payload.source,
        schedule_key=payload.schedule_key,
        series_id=payload.series_id,
        reserve_account_id=payload.reserve_account_id,
    )
    db.add(entry)
    db.commit()
    _post_bank_transaction(db, entry)
    db.commit()
    post_commercial_operation_entry(db, entry)
    return entry


@router.put('/companies/{company_id}/commercial-operations/{entry_id}', response_model=schemas.CommercialOperationEntryOut)
def update_commercial_operation_entry(
    company_id: str,
    entry_id: str,
    payload: schemas.CommercialOperationEntryCreate,
    db: Session = Depends(get_db),
):
    entry = db.query(models.CommercialOperationEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Entry not found')
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail='category must be one of: revenue, cos, expenses')
    if not payload.bank_account_id:
        raise HTTPException(status_code=400, detail='A bank account is required.')
    _validate_reserve_account(payload)

    # Drop the old postings first so they can be cleanly re-derived from the
    # updated values below — same net effect as a delete followed by a
    # fresh create, without touching the entry's id (or its SimParameter
    # flag, which the frontend manages separately).
    unpost_commercial_operation_entry(db, entry_id)
    db.query(models.BankTransaction).filter_by(
        source_type='commercial_operation_entry', source_id=entry_id
    ).delete(synchronize_session=False)
    db.query(models.BankTransaction).filter_by(
        source_type=RESERVE_TRANSFER_SOURCE_TYPE, source_id=entry_id
    ).delete(synchronize_session=False)

    entry.category = payload.category
    entry.entry_date = payload.entry_date
    entry.description = payload.description
    entry.entry_type = payload.entry_type
    entry.client = payload.client
    entry.amount = payload.amount
    entry.accounting_treatment = payload.accounting_treatment
    entry.is_recurring = payload.is_recurring
    entry.is_discount = payload.is_discount
    entry.settlement_date = payload.settlement_date
    entry.bank_account_id = payload.bank_account_id
    entry.reference_document = payload.reference_document
    entry.paid_to = payload.paid_to
    entry.recurrence_frequency = payload.recurrence_frequency
    entry.recurrence_interval = payload.recurrence_interval
    entry.recurrence_custom_unit = payload.recurrence_custom_unit
    entry.recurrence_until_date = payload.recurrence_until_date
    entry.source = payload.source
    entry.schedule_key = payload.schedule_key
    entry.series_id = payload.series_id
    entry.reserve_account_id = payload.reserve_account_id
    db.commit()

    _post_bank_transaction(db, entry)
    db.commit()
    post_commercial_operation_entry(db, entry)
    return entry


@router.delete('/companies/{company_id}/commercial-operations/{entry_id}')
def delete_commercial_operation_entry(company_id: str, entry_id: str, db: Session = Depends(get_db)):
    entry = db.query(models.CommercialOperationEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Entry not found')
    unpost_commercial_operation_entry(db, entry_id)
    db.query(models.SimParameter).filter_by(entry_id=entry_id).delete(synchronize_session=False)
    db.query(models.BankTransaction).filter_by(
        source_type='commercial_operation_entry', source_id=entry_id
    ).delete(synchronize_session=False)
    db.query(models.BankTransaction).filter_by(
        source_type=RESERVE_TRANSFER_SOURCE_TYPE, source_id=entry_id
    ).delete(synchronize_session=False)
    db.delete(entry)
    db.commit()
    return {'ok': True}
