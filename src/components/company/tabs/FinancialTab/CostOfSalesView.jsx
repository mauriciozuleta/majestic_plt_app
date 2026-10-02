import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchSettings } from '../../../../services/settings'
import YearSummaryTable from '../../../shared/YearSummaryTable'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import './ExpensesView.css'

const MONTH_LABELS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12']

function formatUsdWhole(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// Draft of COS/Expenses ▸ Cost of Sales, laid out exactly like the Expenses
// table (Monthly / Year Summary, one row per category, M1–M12 and a Total).
// Not wired yet: there are no COS categories, so `rows` is always empty. Each
// row will take the same {name, months: [12 numbers]} shape the Expenses
// table uses once COS categories and Add COS entries feed it.
function CostOfSalesView() {
  const { companyId } = useParams()
  const [projectionYears, setProjectionYears] = useState(5)
  const [viewMode, setViewMode] = useState('monthly')
  const [selectedYear, setSelectedYear] = useState(1)
  const rows = []

  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    fetchSettings(companyId)
      .then((settings) => {
        if (!cancelled) setProjectionYears(Math.max(5, Math.min(10, Number(settings.projection_years ?? 5))))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [companyId])

  const years = Array.from({ length: projectionYears }, (_, index) => index + 1)
  const monthlyTotals = MONTH_LABELS.map((_, index) => rows.reduce((sum, row) => sum + (row.months[index] || 0), 0))

  return (
    <div className="panel-surface expenses-view">
      <h3>Cost of Sales</h3>

      <div className="expenses-view__toolbar">
        <div className="expenses-view__view-toggle">
          <button type="button" className={viewMode === 'monthly' ? 'is-active' : ''} onClick={() => setViewMode('monthly')}>
            Monthly
          </button>
          <button type="button" className={viewMode === 'yearly' ? 'is-active' : ''} onClick={() => setViewMode('yearly')}>
            Year Summary
          </button>
        </div>

        {viewMode === 'monthly' && (
          <label className="expenses-view__year-selector">
            Projection year
            <select value={selectedYear} onChange={(event) => setSelectedYear(Number(event.target.value))}>
              {years.map((yearNumber) => (
                <option key={yearNumber} value={yearNumber}>
                  Year {yearNumber}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {viewMode === 'yearly' ? (
        <YearSummaryTable years={years} rows={[]} nameHeader="Category" formatValue={formatUsdWhole} />
      ) : (
        <div className="expenses-view__scroll">
          <table className="expenses-view__table">
            <thead>
              <tr>
                <th className="sticky-col">Category</th>
                {MONTH_LABELS.map((label) => (
                  <th key={label} className="num">
                    {label}
                  </th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="sticky-col expenses-view__status" colSpan={MONTH_LABELS.length + 2}>
                    No cost of sales categories yet — they&apos;ll appear here once COS categories and Add COS entries are connected.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.name}>
                    <td className="sticky-col">{row.name}</td>
                    {row.months.map((value, index) => (
                      <td key={index} className="num">
                        {formatUsdWhole(value)}
                      </td>
                    ))}
                    <td className="num">{formatUsdWhole(row.months.reduce((sum, value) => sum + value, 0))}</td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr className="expenses-view__total-row">
                <td className="sticky-col">Total</td>
                {monthlyTotals.map((value, index) => (
                  <td key={index} className="num">
                    {formatUsdWhole(value)}
                  </td>
                ))}
                <td className="num">{formatUsdWhole(monthlyTotals.reduce((sum, value) => sum + value, 0))}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default CostOfSalesView
