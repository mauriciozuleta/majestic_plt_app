import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAccountingReport } from '../../../../../services/accountingReports'
import ReportView from './ReportView'
import './Accounting.css'

function CashFlowStatementView() {
  const { companyId } = useParams()
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const { report, loading, error } = useAccountingReport(companyId, 'cash-flow', { startDate, endDate })

  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>
  if (loading || !report) return <div className="accounting-view__status">Loading cash flow statement...</div>

  const periodsCaption = startDate || endDate ? `${startDate || 'Start'} to ${endDate || 'Today'}` : 'All time'

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
      <ReportView report={report} periodsCaption={periodsCaption} csvFilename="cash-flow-statement.csv" colorBySign scrollRows />
    </div>
  )
}

export default CashFlowStatementView
