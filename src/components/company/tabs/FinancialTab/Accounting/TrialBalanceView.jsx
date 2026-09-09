import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import ExportPdfButton from '../../../../shared/PdfExport/ExportPdfButton'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { fetchChartOfAccounts, fetchJournalEntries } from '../../../../../services/generalLedger'
import { buildTrialBalance, trialBalanceToCsvRows, trialBalanceToPdfSpec } from './accountingReports'
import './Accounting.css'

function money(value) {
  return `$${(Number(value) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function TrialBalanceView() {
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

  const trialBalance = useMemo(() => buildTrialBalance(accounts, journalEntries), [accounts, journalEntries])

  if (loading) return <div className="accounting-view__status">Loading trial balance...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  const handleExportCsv = () => {
    const { headers, rows } = trialBalanceToCsvRows(trialBalance)
    downloadCsv('trial-balance.csv', headers, rows)
  }

  return (
    <div className="accounting-view">
      <div className="accounting-view__toolbar">
        <span className={`accounting-view__badge ${trialBalance.balanced ? 'is-balanced' : 'is-unbalanced'}`}>
          {trialBalance.balanced ? 'Balanced' : 'Out of balance'}
        </span>
        <div className="accounting-view__export-actions">
          <button type="button" className="accounting-view__csv-btn" onClick={handleExportCsv}>
            Export CSV
          </button>
          <ExportPdfButton spec={trialBalanceToPdfSpec(trialBalance, 'All time')} label="Export PDF" />
        </div>
      </div>

      {trialBalance.rows.length === 0 ? (
        <div className="accounting-view__status">No ledger activity yet.</div>
      ) : (
        <table className="accounting-view__table">
          <thead>
            <tr>
              <th>Account</th>
              <th className="num">Debit</th>
              <th className="num">Credit</th>
            </tr>
          </thead>
          <tbody>
            {trialBalance.rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="num">{row.debit ? money(row.debit) : ''}</td>
                <td className="num">{row.credit ? money(row.credit) : ''}</td>
              </tr>
            ))}
            <tr className="report-view__subtotal-row">
              <td>Total</td>
              <td className="num">{money(trialBalance.totalDebit)}</td>
              <td className="num">{money(trialBalance.totalCredit)}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}

export default TrialBalanceView
