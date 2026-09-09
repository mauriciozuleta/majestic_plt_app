import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchChartOfAccounts, fetchJournalEntries } from '../../../../../services/generalLedger'
import { buildIncomeStatement } from './accountingReports'
import ReportView from './ReportView'
import './Accounting.css'

function IncomeStatementView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [journalEntries, setJournalEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

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

  const report = useMemo(
    () => buildIncomeStatement(accounts, journalEntries, { startDate, endDate }),
    [accounts, journalEntries, startDate, endDate],
  )

  if (loading) return <div className="accounting-view__status">Loading income statement...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  const periodsCaption =
    startDate || endDate ? `${startDate || 'Start'} to ${endDate || 'Today'}` : 'All time'

  return (
    <div>
      <div className="accounting-view__date-filter">
        <label>
          From
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
      </div>
      <ReportView report={report} periodsCaption={periodsCaption} csvFilename="income-statement.csv" />
    </div>
  )
}

export default IncomeStatementView
