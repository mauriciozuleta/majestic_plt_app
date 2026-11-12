import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAccountingReport } from '../../../../../services/accountingReports'
import ReportView from './ReportView'
import './Accounting.css'

function IncomeStatementView() {
  const { companyId } = useParams()
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const { report, loading, error } = useAccountingReport(companyId, 'income-statement', { startDate, endDate })

  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>
  if (loading || !report) return <div className="accounting-view__status">Loading income statement...</div>

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
