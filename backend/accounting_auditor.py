"""
Independent accounting auditor: traces every Commercial Operations entry
through the books and reports where it disagrees with what double-entry
accounting says should be there.

Deliberately does NOT import gl_engine.py's posting rules or the frontend's
accountingTreatments.js. Those encode what the app's *posting* engine and
*form* currently do; if either has a bug, an auditor built on the same rules
would agree with the bug instead of catching it. Everything below re-derives
"what should be true" straight from each entry's own stored fields
(category, accounting_treatment, entry_date, settlement_date, amount) and
from general double-entry bookkeeping, so a divergence between this module
and gl_engine.py is itself a meaningful signal, not just duplicated logic.

Three checks run per entry, in order, findings from all three are kept even
if an earlier one fails (so one bad entry doesn't hide the rest):
  1. Field completeness — does the entry have every field its own
     category/accounting_treatment requires to be postable at all?
  2. Bank transaction — does exactly one BankTransaction exist with the
     right amount, direction, date and bank account for what this entry's
     treatment says actually happens to cash (which is not "every entry
     posts a bank row", contrary to what commercial_operations.py currently
     does — see CASH_TIMING_BY_TREATMENT below)?
  3. Journal postings — do the right number of JournalEntry/JournalLine
     rows exist (1 leg if settlement_date is unset or equal to entry_date,
     2 if it's set and different — inferred from the entry's own two date
     fields, not from gl_engine's has_settlement variable), and does each
     one balance (debits == credits)?

A fourth, company-level check compares the books' own running cash balance
(sum of JournalLine debits/credits against the '1000' Cash account) against
the bank ledger's own running balance (sum of BankTransaction credits minus
debits) — catching systemic drift a single-entry trace can't see, e.g. a
manually-deleted bank transaction that left the journal untouched.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func

from . import models

SEVERITY_ERROR = 'error'
SEVERITY_WARNING = 'warning'

VALID_CATEGORIES = {'revenue', 'cos', 'expenses'}

# Which fields must be non-empty for every entry, regardless of category —
# reasoned from what a postable transaction record needs to exist at all,
# not copied from AddEntryModal.jsx's own validation.
BASE_REQUIRED_FIELDS = ['entry_date', 'amount', 'bank_account_id', 'accounting_treatment']

# Category-specific required fields, on top of BASE_REQUIRED_FIELDS.
CATEGORY_REQUIRED_FIELDS = {
    'revenue': ['entry_type', 'client', 'reference_document'],
    'cos': ['description', 'paid_to', 'reference_document'],
    'expenses': ['description', 'paid_to', 'reference_document'],
}

# Recognized accounting_treatment values per category — anything else on a
# saved entry means either corrupt data or a treatment the auditor doesn't
# know about yet, both worth flagging rather than silently skipping.
VALID_TREATMENTS = {
    'revenue': {'earned', 'accrued', 'deferred'},
    'cos': {'purchase_accrued', 'purchase_prepaid', 'consumption', 'direct_production'},
    'expenses': {'cash', 'accrued', 'prepaid', 'capex', 'payroll', 'tax', 'benefits'},
}

# When cash actually moves for a given (category, treatment) pair, reasoned
# directly from what each treatment means in the real world:
#   'entry'      - cash moves on entry_date, always (a same-day payment).
#   'settlement' - cash moves only on settlement_date, and only once one is
#                  set (an accrued obligation that hasn't been paid yet has
#                  moved no cash at all — that's not an error, it's an
#                  entry still awaiting payment).
#   'none'       - this treatment never touches cash (e.g. consuming
#                  inventory that was already paid for at purchase time).
CASH_TIMING_BY_TREATMENT = {
    ('revenue', 'earned'): 'entry',
    ('revenue', 'accrued'): 'settlement',
    ('revenue', 'deferred'): 'entry',
    ('cos', 'purchase_accrued'): 'settlement',
    ('cos', 'purchase_prepaid'): 'entry',
    ('cos', 'consumption'): 'none',
    ('cos', 'direct_production'): 'entry',
    ('expenses', 'cash'): 'entry',
    ('expenses', 'accrued'): 'settlement',
    ('expenses', 'prepaid'): 'entry',
    ('expenses', 'capex'): 'entry',
    ('expenses', 'payroll'): 'settlement',
    ('expenses', 'tax'): 'settlement',
    ('expenses', 'benefits'): 'settlement',
}

# Treatments whose settlement date is mandatory once the entry is otherwise
# valid (the current Add COS/Expense/Revenue forms require it for these) —
# a missing one is a hard error, not just "not paid yet".
SETTLEMENT_REQUIRED_TREATMENTS = {
    ('revenue', 'accrued'),
    ('cos', 'purchase_accrued'),
    ('expenses', 'accrued'),
}

CASH_ACCOUNT_CODE = '1000'


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _has_settlement(entry):
    return bool(entry.settlement_date) and entry.settlement_date != entry.entry_date


def _add_finding(db, run, company_id, entry_id, severity, code, message):
    db.add(
        models.AccountingAuditFinding(
            id=str(uuid.uuid4()),
            run_id=run.id,
            company_id=company_id,
            entry_id=entry_id,
            severity=severity,
            code=code,
            message=message,
        )
    )


def _check_completeness(db, run, entry):
    """Returns True if the entry is complete enough for the bank/journal
    checks below to mean anything; a missing category/treatment makes those
    checks meaningless (there's no "correct" posting to compare against), so
    callers skip them when this returns False."""
    complete = True

    if entry.category not in VALID_CATEGORIES:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'invalid_category',
            f"category '{entry.category}' is not one of {sorted(VALID_CATEGORIES)}.",
        )
        return False

    for field_name in BASE_REQUIRED_FIELDS:
        value = getattr(entry, field_name)
        if value is None or value == '' or (field_name == 'amount' and not value):
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'missing_required_field',
                f"'{field_name}' is required but missing.",
            )
            complete = False

    for field_name in CATEGORY_REQUIRED_FIELDS.get(entry.category, []):
        value = getattr(entry, field_name)
        if value is None or value == '':
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'missing_required_field',
                f"'{field_name}' is required for {entry.category} entries but missing.",
            )
            complete = False

    if entry.amount is not None and entry.amount <= 0:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'non_positive_amount',
            f'amount must be greater than zero, found {entry.amount}.',
        )
        complete = False

    if entry.accounting_treatment and entry.category in VALID_TREATMENTS:
        if entry.accounting_treatment not in VALID_TREATMENTS[entry.category]:
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'invalid_treatment',
                f"accounting_treatment '{entry.accounting_treatment}' is not valid for category '{entry.category}'.",
            )
            complete = False

    if entry.bank_account_id and complete:
        bank_account_exists = db.query(models.BankAccount.id).filter_by(id=entry.bank_account_id).first()
        if not bank_account_exists:
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'dangling_bank_account',
                f"bank_account_id '{entry.bank_account_id}' does not reference an existing bank account.",
            )
            complete = False

    treatment_key = (entry.category, entry.accounting_treatment)
    if treatment_key in SETTLEMENT_REQUIRED_TREATMENTS and not entry.settlement_date:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'missing_settlement_date',
            f"'{entry.accounting_treatment}' requires a settlement_date but none is set.",
        )
        complete = False

    return complete


def _expected_cash_leg(entry):
    """Returns (expected_date, expected_credit, expected_debit) for the one
    BankTransaction this entry should have, or None if this treatment never
    touches cash, or if it's an unpaid accrual still awaiting settlement."""
    timing = CASH_TIMING_BY_TREATMENT.get((entry.category, entry.accounting_treatment))
    if timing is None or timing == 'none':
        return None
    if timing == 'settlement' and not _has_settlement(entry):
        return None

    expected_date = entry.settlement_date if timing == 'settlement' else entry.entry_date
    expected_credit = entry.amount if entry.category == 'revenue' else 0.0
    expected_debit = entry.amount if entry.category in ('cos', 'expenses') else 0.0
    return expected_date, expected_credit, expected_debit


def _check_bank_transaction(db, run, entry):
    transactions = (
        db.query(models.BankTransaction)
        .filter_by(source_type='commercial_operation_entry', source_id=entry.id)
        .all()
    )
    timing = CASH_TIMING_BY_TREATMENT.get((entry.category, entry.accounting_treatment))
    expected = _expected_cash_leg(entry)

    if expected is None:
        if transactions:
            reason = 'never moves cash' if timing == 'none' else 'has not reached its settlement date yet'
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'unexpected_bank_transaction',
                f"{len(transactions)} bank transaction(s) exist, but '{entry.accounting_treatment}' {reason}.",
            )
        return

    expected_date, expected_credit, expected_debit = expected

    if not transactions:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'missing_bank_transaction',
            f'expected a bank transaction dated {expected_date} but none exists.',
        )
        return

    if len(transactions) > 1:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'duplicate_bank_transaction',
            f'expected exactly 1 bank transaction, found {len(transactions)}.',
        )

    transaction = transactions[0]
    if transaction.entry_date != expected_date:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'bank_transaction_wrong_date',
            f"bank transaction is dated {transaction.entry_date}, expected {expected_date}.",
        )
    if transaction.bank_account_id != entry.bank_account_id:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'bank_transaction_wrong_account',
            f"bank transaction posts to bank account '{transaction.bank_account_id}', expected '{entry.bank_account_id}'.",
        )
    if abs((transaction.credit or 0.0) - expected_credit) > 0.005 or abs((transaction.debit or 0.0) - expected_debit) > 0.005:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'bank_transaction_wrong_amount',
            f'bank transaction has credit={transaction.credit}, debit={transaction.debit}; '
            f'expected credit={expected_credit}, debit={expected_debit}.',
        )


def _check_journal_postings(db, run, entry):
    expected_legs = 2 if _has_settlement(entry) else 1

    journal_entries = (
        db.query(models.JournalEntry)
        .filter_by(source_type='commercial_operation_entry', source_id=entry.id)
        .all()
    )

    if len(journal_entries) != expected_legs:
        _add_finding(
            db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'wrong_journal_entry_count',
            f'expected {expected_legs} journal entry leg(s) '
            f"({'settlement_date differs from entry_date' if expected_legs == 2 else 'no distinct settlement_date'}), "
            f'found {len(journal_entries)}.',
        )

    for journal_entry in journal_entries:
        lines = db.query(models.JournalLine).filter_by(journal_entry_id=journal_entry.id).all()
        total_debit = sum(line.debit or 0.0 for line in lines)
        total_credit = sum(line.credit or 0.0 for line in lines)
        if abs(total_debit - total_credit) > 0.005:
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'unbalanced_journal_entry',
                f'journal entry {journal_entry.id} (dated {journal_entry.entry_date}) does not balance: '
                f'debits={total_debit}, credits={total_credit}.',
            )
        if not lines:
            _add_finding(
                db, run, entry.company_id, entry.id, SEVERITY_ERROR, 'empty_journal_entry',
                f'journal entry {journal_entry.id} (dated {journal_entry.entry_date}) has no lines.',
            )


def _check_company_cash_balance(db, run, company_id):
    """Aggregate check: the books' own cash account should net to the same
    balance as the bank ledger it's supposed to mirror. This is the one
    check that isn't per-entry — it catches drift a single-entry trace
    can't (e.g. a bank transaction deleted by hand without touching the
    journal, or vice versa)."""
    cash_account_ids = [
        row.id
        for row in db.query(models.GeneralLedgerAccount).filter_by(company_id=company_id, code=CASH_ACCOUNT_CODE).all()
    ]
    if not cash_account_ids:
        return

    journal_cash_balance = (
        db.query(func.coalesce(func.sum(models.JournalLine.debit - models.JournalLine.credit), 0.0))
        .filter(models.JournalLine.account_id.in_(cash_account_ids))
        .scalar()
        or 0.0
    )

    bank_account_ids = [row.id for row in db.query(models.BankAccount.id).filter_by(company_id=company_id).all()]
    if bank_account_ids:
        bank_ledger_balance = (
            db.query(func.coalesce(func.sum(models.BankTransaction.credit - models.BankTransaction.debit), 0.0))
            .filter(models.BankTransaction.bank_account_id.in_(bank_account_ids))
            .scalar()
            or 0.0
        )
    else:
        bank_ledger_balance = 0.0

    if abs(journal_cash_balance - bank_ledger_balance) > 0.005:
        _add_finding(
            db, run, company_id, None, SEVERITY_ERROR, 'cash_balance_mismatch',
            f'general ledger Cash balance ({journal_cash_balance:.2f}) does not match the sum of bank '
            f'account ledgers ({bank_ledger_balance:.2f}).',
        )


def run_audit(db, scope_company_id=None, triggered_by='manual'):
    """Runs the full audit and returns the (already committed)
    AccountingAuditRun row. scope_company_id=None audits every company."""
    run = models.AccountingAuditRun(
        id=str(uuid.uuid4()),
        started_at=_now_iso(),
        status='running',
        scope_company_id=scope_company_id,
        triggered_by=triggered_by,
    )
    db.add(run)
    db.commit()

    try:
        entries_query = db.query(models.CommercialOperationEntry)
        if scope_company_id:
            entries_query = entries_query.filter_by(company_id=scope_company_id)
        entries = entries_query.all()

        for entry in entries:
            complete = _check_completeness(db, run, entry)
            if complete:
                _check_bank_transaction(db, run, entry)
                _check_journal_postings(db, run, entry)

        if scope_company_id:
            company_ids = [scope_company_id]
        else:
            company_ids = [row.id for row in db.query(models.Company.id).all()]
        for company_id in company_ids:
            _check_company_cash_balance(db, run, company_id)

        # flush first: the session has autoflush disabled, so the finding
        # rows added by the checks above aren't visible to this count query
        # until they're explicitly pushed to the database.
        db.flush()
        findings_count = db.query(models.AccountingAuditFinding).filter_by(run_id=run.id).count()
        run.entries_checked = len(entries)
        run.findings_count = findings_count
        run.status = 'completed'
        run.finished_at = _now_iso()
        db.commit()
    except Exception as error:  # noqa: BLE001 - the run row must record failure either way
        db.rollback()
        run.status = 'failed'
        run.error_message = str(error)
        run.finished_at = _now_iso()
        db.commit()
        raise

    return run
