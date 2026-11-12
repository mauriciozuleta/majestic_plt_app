import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAccountingReport } from '../../../../../services/accountingReports'
import ReportView from './ReportView'
import './Accounting.css'

function BalanceSheetView() {
  const { companyId } = useParams()
  const [asOfDate, setAsOfDate] = useState('')

  const { report, loading, error } = useAccountingReport(companyId, 'balance-sheet', { asOfDate })

  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>
  if (loading || !report) return <div className="accounting-view__status">Loading balance sheet...</div>

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
