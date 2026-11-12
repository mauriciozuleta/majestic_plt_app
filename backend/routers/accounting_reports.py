"""Financial statements API (backend/accounting_reports/): trial balance, income statement, balance sheet, cash flow statement and the condensed general-ledger summary of a
company, derived from its chart of accounts and journal entries. Moved from the browser; the numbers equal what the JavaScript gave (backend/tests/test_accounting_reports_parity.py).
All read-only (tier R)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..accounting_reports import service
from ..database import get_db

router = APIRouter(tags=['accounting-reports'])


@router.get('/companies/{company_id}/gl/reports/{kind}')
def get_report(company_id: str, kind: str, start_date: str | None = None, end_date: str | None = None, as_of_date: str | None = None, db: Session = Depends(get_db)):
    """Tier R. `kind`: trial-balance | income-statement | balance-sheet | cash-flow | general-ledger-summary. `start_date` / `end_date` (inclusive, YYYY-MM-DD) limit the income
    statement and the cash flow statement; `as_of_date` limits the balance sheet. Without dates the statement covers the whole ledger."""
    if kind not in service.KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown statement '{kind}'. One of: {', '.join(service.KINDS)}.")
    return service.statement(db, company_id, kind, start_date, end_date, as_of_date)
