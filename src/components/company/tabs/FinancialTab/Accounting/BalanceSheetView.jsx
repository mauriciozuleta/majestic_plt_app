import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchChartOfAccounts, fetchJournalEntries } from '../../../../../services/generalLedger'
import { buildBalanceSheet } from './accountingReports'
import ReportView from './ReportView'
import './Accounting.css'

function BalanceSheetView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [journalEntries, setJournalEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [asOfDate, setAsOfDate] = useState('')

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

  const report = useMemo(() => buildBalanceSheet(accounts, journalEntries, { asOfDate }), [accounts, journalEntries, asOfDate])

  if (loading) return <div className="accounting-view__status">Loading balance sheet...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  return (
    <div>
      <div className="accounting-view__date-filter">
        <label>
          As of
          <input type="date" value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} />
        </label>
      </div>
      <ReportView
        report={report}
        periodsCaption={asOfDate ? `As of ${asOfDate}` : 'As of today'}
        csvFilename="balance-sheet.csv"
        balanced={report.sections.length > 0 ? report.balanced : undefined}
      />
    </div>
  )
}

export default BalanceSheetView
