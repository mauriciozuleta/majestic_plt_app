import { useEffect, useState } from 'react'
import { fetchPayroll } from '../../../../../services/payroll'
import { positionMonthlyHeadcount } from './monthMath'
import YearSummaryTable from '../../../../shared/YearSummaryTable'

/** One column per projection year (a position's annual cost that year),
 * instead of stepping through years one at a time via the year dropdown. */
function PayrollYearSummary({ companyId, projectionYears, calendarMode }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const years = Array.from({ length: projectionYears + 1 }, (_, index) => index)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    Promise.all(years.map((year) => fetchPayroll(companyId, year)))
      .then((allYearsRows) => {
        if (cancelled) return

        const byNode = new Map()
        allYearsRows.forEach((yearRows, yearIndex) => {
          yearRows.forEach((row) => {
            if (!byNode.has(row.node_id)) {
              byNode.set(row.node_id, { label: row.office_name, totalsByYear: new Array(years.length).fill(0) })
            }
            const months = positionMonthlyHeadcount(row.employees || [], years[yearIndex], calendarMode)
            const annualTotal = months.reduce((sum, headcount) => sum + Math.round((row.year_salary * headcount) / 12), 0)
            byNode.get(row.node_id).totalsByYear[yearIndex] = annualTotal
          })
        })
        setRows(Array.from(byNode.values()))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, projectionYears, calendarMode])

  if (loading) return <div className="payroll-view__status">Loading year summary...</div>

  return <YearSummaryTable years={years} rows={rows} nameHeader="Position" formatValue={(value) => `$${Math.round(value).toLocaleString()}`} />
}

export default PayrollYearSummary
