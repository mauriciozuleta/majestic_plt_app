// Financial statements: trial balance, income statement, balance sheet, cash flow statement. Worked out on the SERVER now (backend/accounting_reports/,
// GET /companies/{id}/gl/reports/{kind}); a parity test (backend/tests/test_accounting_reports_parity.py) holds the Python to exactly the numbers the old JavaScript gave.
// This file only asks for them.
import { useEffect, useState } from 'react'
import { API_BASE } from './apiBase'

/** kind: 'trial-balance' | 'income-statement' | 'balance-sheet' | 'cash-flow' | 'general-ledger-summary'; params: { startDate, endDate, asOfDate } (empty = the whole ledger) */
export async function fetchAccountingReport(companyId, kind, { startDate = '', endDate = '', asOfDate = '' } = {}) {
  const query = new URLSearchParams()
  if (startDate) query.set('start_date', startDate)
  if (endDate) query.set('end_date', endDate)
  if (asOfDate) query.set('as_of_date', asOfDate)
  const response = await fetch(`${API_BASE}/companies/${companyId}/gl/reports/${kind}?${query}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Failed to load the ${kind.replace('-', ' ')}`)
  }
  return response.json()
}

/** -> { report, loading, error }; asks again when the company or a date changes. `loading` is true until the first answer arrives, so a date change keeps the last report on screen. */
export function useAccountingReport(companyId, kind, { startDate = '', endDate = '', asOfDate = '' } = {}) {
  const [state, setState] = useState({ report: null, loading: true, error: '' })
  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    fetchAccountingReport(companyId, kind, { startDate, endDate, asOfDate })
      .then((report) => !cancelled && setState({ report, loading: false, error: '' }))
      .catch((err) => !cancelled && setState((prev) => ({ ...prev, loading: false, error: err.message })))
    return () => {
      cancelled = true
    }
  }, [companyId, kind, startDate, endDate, asOfDate])
  return state
}
