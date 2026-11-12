"""Loads a company's ledger from the database and builds one of the statements."""

from . import reports

KINDS = ('trial-balance', 'income-statement', 'balance-sheet', 'cash-flow', 'general-ledger-summary')


def ledger_of(db, company_id: str) -> tuple[list[dict], list[dict]]:
    """(accounts, entries) as the plain dicts the statements work on — the same data the General Ledger screen reads."""
    from ..routers.general_ledger import list_accounts, list_journal_entries

    accounts = [{'id': a.id, 'code': a.code, 'name': a.name, 'account_type': a.account_type, 'normal_balance': a.normal_balance} for a in list_accounts(company_id, db)]
    entries = [{'entry_date': e.entry_date, 'memo': e.memo, 'lines': [{'account_id': line.account_id, 'debit': line.debit, 'credit': line.credit} for line in e.lines]}
               for e in list_journal_entries(company_id, db)]
    return accounts, entries


def statement(db, company_id: str, kind: str, start_date: str | None = None, end_date: str | None = None, as_of_date: str | None = None) -> dict:
    """`kind` is one of KINDS. `start_date` / `end_date` (inclusive, ISO) limit the income statement and the cash flow; `as_of_date` limits the balance sheet."""
    if kind not in KINDS:
        raise ValueError(f'Unknown statement: {kind}')
    accounts, entries = ledger_of(db, company_id)
    if kind == 'trial-balance':
        return reports.build_trial_balance(accounts, entries)
    if kind == 'income-statement':
        return reports.build_income_statement(accounts, entries, start_date, end_date)
    if kind == 'balance-sheet':
        return reports.build_balance_sheet(accounts, entries, as_of_date)
    if kind == 'cash-flow':
        return reports.build_cash_flow_statement(accounts, entries, start_date, end_date)
    return reports.build_general_ledger_summary(accounts, entries)
