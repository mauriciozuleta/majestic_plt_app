import { useEffect, useState } from 'react'
import { fetchPayroll } from '../../../../../services/payroll'
import { positionMonthlyHeadcount } from './monthMath'
import YearSummaryTable from '../../../../shared/YearSummaryTable'
import { usePayrollCurrencyRates } from '../../../../../hooks/usePayrollCurrencyRates'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { formatLocalCurrencyForLocation, formatLocalCurrencyForRows } from '../../../../../utils/payrollLocalCurrency'

function formatUsdWhole(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

/** One column per projection year (a position's annual cost that year),
 * instead of stepping through years one at a time via the year dropdown. */
function PayrollYearSummary({ companyId, projectionYears, calendarMode }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const years = Array.from({ length: projectionYears }, (_, index) => index + 1)
  const rates = usePayrollCurrencyRates()

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
              byNode.set(row.node_id, {
                label: row.office_name,
                location: row.location,
                totalsByYear: new Array(years.length).fill(0),
              })
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

  return (
    <YearSummaryTable
      years={years}
      rows={rows}
      nameHeader="Position"
      formatValue={formatUsdWhole}
      formatSubValue={(row, value) => formatLocalCurrencyForLocation(row.location, value, rates)}
      formatTotalSubValue={(_value, yearIndex) =>
        formatLocalCurrencyForRows(rows, (row) => row.totalsByYear[yearIndex] || 0, rates)
      }
    />
  )
}

export default PayrollYearSummary
