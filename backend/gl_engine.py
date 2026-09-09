"""
Double-entry posting engine that turns a categorized Commercial Operations
entry (category + accounting_treatment, set in the Add Revenue/COS/Expense
forms) into journal entries against a per-company chart of accounts.

Each company gets a standard chart of accounts lazily seeded on first use.
Posting an entry with no accounting_treatment (older data, or a category the
rules below don't cover) is a no-op — nothing breaks, it's just not on the
ledger yet.
"""

import uuid
from datetime import date

from . import models

FICTITIOUS_EPOCH = date(1, 1, 1)

# (code, name, account_type, normal_balance)
DEFAULT_ACCOUNTS = [
    ('1000', 'Cash', 'asset', 'debit'),
    ('1100', 'Accounts Receivable', 'asset', 'debit'),
    ('1200', 'Inventory', 'asset', 'debit'),
    ('1250', 'Prepaid Inventory', 'asset', 'debit'),
    ('1300', 'Prepaid Expenses', 'asset', 'debit'),
    ('1500', 'Fixed Assets', 'asset', 'debit'),
    ('2000', 'Accounts Payable', 'liability', 'credit'),
    ('2100', 'Unearned Revenue', 'liability', 'credit'),
    ('2200', 'Payroll Payable', 'liability', 'credit'),
    ('2300', 'Tax Payable', 'liability', 'credit'),
    ('3000', "Owner's Capital", 'equity', 'credit'),
    ('4000', 'Revenue', 'revenue', 'credit'),
    ('4900', 'Discounts & Promotions', 'contra_revenue', 'debit'),
    ('5000', 'Cost of Goods Sold', 'expense', 'debit'),
    ('5900', 'Direct Production Cost', 'expense', 'debit'),
    ('6000', 'Operating Expenses', 'expense', 'debit'),
    ('6100', 'Payroll Expense', 'expense', 'debit'),
    ('6200', 'Tax Expense', 'expense', 'debit'),
]

OPENING_BALANCE_SOURCE_TYPE = 'startup_investment_opening_balance'


def ensure_default_accounts(db, company_id):
    """Returns {code: account_id}, seeding the standard chart of accounts for
    this company the first time it's needed — and adding any accounts that
    were added to DEFAULT_ACCOUNTS after this company's chart was first
    seeded, so an existing company picks up new default accounts too."""
    existing = db.query(models.GeneralLedgerAccount).filter_by(company_id=company_id).all()
    by_code = {account.code: account.id for account in existing}

    added = False
    for code, name, account_type, normal_balance in DEFAULT_ACCOUNTS:
        if code in by_code:
            continue
        account = models.GeneralLedgerAccount(
            id=str(uuid.uuid4()),
            company_id=company_id,
            code=code,
            name=name,
            account_type=account_type,
            normal_balance=normal_balance,
        )
        db.add(account)
        by_code[code] = account.id
        added = True

    if added:
        db.commit()
    return by_code


def _make_journal_entry(db, company_id, entry_date, memo, source_id, lines, accounts_by_code, source_type='commercial_operation_entry'):
    journal_entry = models.JournalEntry(
        id=str(uuid.uuid4()),
        company_id=company_id,
        entry_date=entry_date,
        memo=memo,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(journal_entry)
    db.flush()

    for code, debit, credit in lines:
        db.add(
            models.JournalLine(
                id=str(uuid.uuid4()),
                journal_entry_id=journal_entry.id,
                account_id=accounts_by_code[code],
                debit=debit,
                credit=credit,
            )
        )


def post_commercial_operation_entry(db, entry):
    """entry: a saved models.CommercialOperationEntry. Posts the initial
    recognition journal entry and, if a settlement_date is set and differs
    from entry_date, the follow-on settlement journal entry too."""
    if not entry.accounting_treatment:
        return

    accounts = ensure_default_accounts(db, entry.company_id)
    amount = entry.amount
    memo = entry.description or entry.entry_type or entry.client or entry.category
    has_settlement = bool(entry.settlement_date) and entry.settlement_date != entry.entry_date
    category = entry.category
    treatment = entry.accounting_treatment

    if category == 'revenue':
        revenue_code = '4900' if entry.is_discount else '4000'
        if treatment == 'earned':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1000', amount, 0), (revenue_code, 0, amount)], accounts)
        elif treatment == 'accrued':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1100', amount, 0), (revenue_code, 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Collect A/R: {memo}', entry.id, [('1000', amount, 0), ('1100', 0, amount)], accounts)
        elif treatment == 'deferred':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1000', amount, 0), ('2100', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Recognize deferred revenue: {memo}', entry.id, [('2100', amount, 0), (revenue_code, 0, amount)], accounts)

    elif category == 'cos':
        if treatment == 'purchase_accrued':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1200', amount, 0), ('2000', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Pay A/P: {memo}', entry.id, [('2000', amount, 0), ('1000', 0, amount)], accounts)
        elif treatment == 'purchase_prepaid':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1250', amount, 0), ('1000', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Receive goods: {memo}', entry.id, [('1200', amount, 0), ('1250', 0, amount)], accounts)
        elif treatment == 'consumption':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('5000', amount, 0), ('1200', 0, amount)], accounts)
        elif treatment == 'direct_production':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('5900', amount, 0), ('1000', 0, amount)], accounts)

    elif category == 'expenses':
        if treatment == 'cash':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('6000', amount, 0), ('1000', 0, amount)], accounts)
        elif treatment == 'accrued':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('6000', amount, 0), ('2000', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Pay A/P: {memo}', entry.id, [('2000', amount, 0), ('1000', 0, amount)], accounts)
        elif treatment == 'prepaid':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1300', amount, 0), ('1000', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Recognize prepaid expense: {memo}', entry.id, [('6000', amount, 0), ('1300', 0, amount)], accounts)
        elif treatment == 'capex':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('1500', amount, 0), ('1000', 0, amount)], accounts)
        elif treatment == 'payroll':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('6100', amount, 0), ('2200', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Pay payroll: {memo}', entry.id, [('2200', amount, 0), ('1000', 0, amount)], accounts)
        elif treatment == 'tax':
            _make_journal_entry(db, entry.company_id, entry.entry_date, memo, entry.id, [('6200', amount, 0), ('2300', 0, amount)], accounts)
            if has_settlement:
                _make_journal_entry(db, entry.company_id, entry.settlement_date, f'Pay tax: {memo}', entry.id, [('2300', amount, 0), ('1000', 0, amount)], accounts)

    db.commit()


def unpost_commercial_operation_entry(db, entry_id):
    """Removes any journal entries (and their lines) posted for this
    commercial-operations entry — used when the entry itself is deleted."""
    journal_entry_ids = [
        row.id for row in db.query(models.JournalEntry).filter_by(source_type='commercial_operation_entry', source_id=entry_id).all()
    ]
    if not journal_entry_ids:
        return
    db.query(models.JournalLine).filter(models.JournalLine.journal_entry_id.in_(journal_entry_ids)).delete(synchronize_session=False)
    db.query(models.JournalEntry).filter(models.JournalEntry.id.in_(journal_entry_ids)).delete(synchronize_session=False)
    db.commit()


def _operations_start_date(db):
    """Year 1, Day 1 — the moment operations begin, right after the
    pre-operational period (which now lives entirely in Start-up Investment,
    not on this calendar at all). Year 1 is the *first* operational year, so
    in simulation mode this is the fictitious epoch itself, day zero — same
    convention as isoDateToSimDate/simDateToIsoDate on the frontend. Real
    mode has no equivalent fictitious "day zero", so it falls back to today."""
    settings = db.query(models.PortfolioSettings).filter_by(id='singleton').first()
    calendar_mode = settings.calendar_mode if settings else 'real'
    if calendar_mode == 'simulation':
        return FICTITIOUS_EPOCH.isoformat()
    return date.today().isoformat()


def sync_opening_balance(db, company_id):
    """(Re)posts the opening-cash journal entry from the company's Total
    Start-up Working Capital — the cash sitting in the bank the moment
    operations begin. Called after every Start-up Investment plan/record
    change; deletes and re-derives the single synthetic entry each time so it
    can never drift out of sync with the working-capital total."""
    existing_ids = [
        row.id
        for row in db.query(models.JournalEntry)
        .filter_by(company_id=company_id, source_type=OPENING_BALANCE_SOURCE_TYPE, source_id=company_id)
        .all()
    ]
    if existing_ids:
        db.query(models.JournalLine).filter(models.JournalLine.journal_entry_id.in_(existing_ids)).delete(synchronize_session=False)
        db.query(models.JournalEntry).filter(models.JournalEntry.id.in_(existing_ids)).delete(synchronize_session=False)

    working_capital_records = (
        db.query(models.StartupInvestmentRecord).filter_by(company_id=company_id, category='working_capital').all()
    )
    total = sum(record.total_amount for record in working_capital_records)

    if total > 0:
        accounts = ensure_default_accounts(db, company_id)
        _make_journal_entry(
            db,
            company_id,
            _operations_start_date(db),
            'Opening cash - Total Start-up Working Capital',
            company_id,
            [('1000', total, 0), ('3000', 0, total)],
            accounts,
            source_type=OPENING_BALANCE_SOURCE_TYPE,
        )

    db.commit()
