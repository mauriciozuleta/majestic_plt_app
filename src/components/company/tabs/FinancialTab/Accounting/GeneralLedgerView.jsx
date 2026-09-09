import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import ExportPdfButton from '../../../../shared/PdfExport/ExportPdfButton'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { fetchChartOfAccounts, fetchJournalEntries } from '../../../../../services/generalLedger'
import { buildGeneralLedgerSummary, generalLedgerToCsvRows, reportToPdfSpec } from './accountingReports'
import './Accounting.css'

const TYPE_LABELS = {
  asset: 'Assets',
  liability: 'Liabilities',
  equity: 'Equity',
  revenue: 'Revenue',
  contra_revenue: 'Contra-Revenue',
  expense: 'Expenses',
}
const TYPE_ORDER = ['asset', 'liability', 'equity', 'revenue', 'contra_revenue', 'expense']

function money(value) {
  const amount = Number(value) || 0
  return `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function GeneralLedgerView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [journalEntries, setJournalEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    setError('')
    Promise.all([fetchChartOfAccounts(companyId), fetchJournalEntries(companyId)])
      .then(([nextAccounts, nextJournalEntries]) => {
        setAccounts(nextAccounts)
        setJournalEntries(nextJournalEntries)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [companyId])

  const ledgerByAccount = useMemo(() => {
    const postings = new Map()
    journalEntries.forEach((entry) => {
      entry.lines.forEach((line) => {
        const list = postings.get(line.account_id) || []
        list.push({ date: entry.entry_date, memo: entry.memo, debit: line.debit, credit: line.credit })
        postings.set(line.account_id, list)
      })
    })
    postings.forEach((list) => list.sort((a, b) => a.date.localeCompare(b.date)))
    return postings
  }, [journalEntries])

  const groupedAccounts = useMemo(() => {
    const groups = new Map(TYPE_ORDER.map((type) => [type, []]))
    accounts
      .filter((account) => (ledgerByAccount.get(account.id) || []).length > 0)
      .forEach((account) => {
        const list = groups.get(account.account_type) || []
        list.push(account)
        groups.set(account.account_type, list)
      })
    return TYPE_ORDER.map((type) => ({ type, accounts: groups.get(type) || [] })).filter((group) => group.accounts.length > 0)
  }, [accounts, ledgerByAccount])

  if (loading) return <div className="accounting-view__status">Loading general ledger...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  const handleExportCsv = () => {
    const { headers, rows } = generalLedgerToCsvRows(accounts, journalEntries)
    downloadCsv('general-ledger.csv', headers, rows)
  }

  if (groupedAccounts.length === 0) {
    return (
      <div className="accounting-view__status">
        No ledger activity yet. Postings appear here automatically once a Commercial Operations entry is saved with an
        Accounting Treatment selected.
      </div>
    )
  }

  return (
    <div className="accounting-view general-ledger">
      <div className="accounting-view__toolbar">
        <div className="accounting-view__export-actions">
          <button type="button" className="accounting-view__csv-btn" onClick={handleExportCsv}>
            Export CSV
          </button>
          <ExportPdfButton spec={reportToPdfSpec(buildGeneralLedgerSummary(accounts, journalEntries), 'All time')} label="Export PDF" />
        </div>
      </div>
      {groupedAccounts.map((group) => (
        <div key={group.type} className="general-ledger__group">
          <h4 className="general-ledger__group-title">{TYPE_LABELS[group.type] ?? group.type}</h4>
          {group.accounts.map((account) => {
            const postings = ledgerByAccount.get(account.id) || []
            let balance = 0
            return (
              <div key={account.id} className="general-ledger__account">
                <div className="general-ledger__account-title">
                  <span className="general-ledger__account-code">{account.code}</span>
                  {account.name}
                </div>
                <table className="accounting-view__table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Memo</th>
                      <th className="num">Debit</th>
                      <th className="num">Credit</th>
                      <th className="num">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {postings.map((posting, index) => {
                      const delta =
                        account.normal_balance === 'debit'
                          ? posting.debit - posting.credit
                          : posting.credit - posting.debit
                      balance += delta
                      return (
                        <tr key={index}>
                          <td>{posting.date}</td>
                          <td>{posting.memo}</td>
                          <td className="num">{posting.debit ? money(posting.debit) : ''}</td>
                          <td className="num">{posting.credit ? money(posting.credit) : ''}</td>
                          <td className="num">{money(balance)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export default GeneralLedgerView
