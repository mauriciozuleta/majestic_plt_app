import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { fetchChartOfAccounts } from '../../../../../services/generalLedger'
import { chartOfAccountsToCsvRows } from './accountingReports'
import './Accounting.css'

const TYPE_LABELS = {
  asset: 'Asset',
  liability: 'Liability',
  equity: 'Equity',
  revenue: 'Revenue',
  contra_revenue: 'Contra-Revenue',
  expense: 'Expense',
}

function ChartOfAccountsView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    fetchChartOfAccounts(companyId)
      .then(setAccounts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [companyId])

  if (loading) return <div className="accounting-view__status">Loading chart of accounts...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  const handleExportCsv = () => {
    const { headers, rows } = chartOfAccountsToCsvRows(accounts)
    downloadCsv('chart-of-accounts.csv', headers, rows)
  }

  return (
    <div className="accounting-view">
      <div className="accounting-view__toolbar">
        <div className="accounting-view__export-actions">
          <button type="button" className="accounting-view__csv-btn" onClick={handleExportCsv}>
            Export CSV
          </button>
        </div>
      </div>
      <table className="accounting-view__table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Name</th>
            <th>Type</th>
            <th>Normal Balance</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((account) => (
            <tr key={account.id}>
              <td className="num">{account.code}</td>
              <td>{account.name}</td>
              <td>{TYPE_LABELS[account.account_type] ?? account.account_type}</td>
              <td className="accounting-view__capitalize">{account.normal_balance}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ChartOfAccountsView
