import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchExpenses, saveExpenseEntry } from '../../../../services/expenses'
import { fetchPayroll } from '../../../../services/payroll'
import { fetchSettings } from '../../../../services/settings'
import { positionMonthlyHeadcount } from '../ManagementTab/PayrollView/monthMath'
import YearSummaryTable from '../../../shared/YearSummaryTable'
import './ExpensesView.css'

const MONTH_LABELS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12']
const PAYROLL_CATEGORY_NAME = 'Payroll'

function computePayrollMonthlyCost(payrollRows, year, calendarMode) {
  const totals = new Array(12).fill(0)
  payrollRows.forEach((row) => {
    const months = positionMonthlyHeadcount(row.employees || [], year, calendarMode)
    months.forEach((headcount, index) => {
      totals[index] += Math.round((row.year_salary * headcount) / 12)
    })
  })
  return totals
}

function ExpensesView() {
  const { companyId } = useParams()
  const [calendarMode, setCalendarMode] = useState('real')
  const [projectionYears, setProjectionYears] = useState(5)
  const [viewMode, setViewMode] = useState('monthly')
  const [selectedYear, setSelectedYear] = useState(0)
  const [entries, setEntries] = useState([])
  const [payrollRows, setPayrollRows] = useState([])
  const [drafts, setDrafts] = useState(() => new Map())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [yearSummaryRows, setYearSummaryRows] = useState([])
  const [yearSummaryLoading, setYearSummaryLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setCalendarMode(settings.calendar_mode ?? 'real')
        setProjectionYears(Math.max(5, Math.min(10, Number(settings.projection_years ?? 5))))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const reloadMonthly = useCallback(async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [nextEntries, nextPayrollRows] = await Promise.all([
        fetchExpenses(companyId, selectedYear),
        fetchPayroll(companyId, selectedYear),
      ])
      setEntries(nextEntries)
      setPayrollRows(nextPayrollRows)
      setDrafts(new Map())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [companyId, selectedYear])

  useEffect(() => {
    if (viewMode === 'monthly') reloadMonthly()
  }, [viewMode, reloadMonthly])

  useEffect(() => {
    if (viewMode !== 'yearly' || !companyId) return undefined
    let cancelled = false
    setYearSummaryLoading(true)
    const years = Array.from({ length: projectionYears + 1 }, (_, index) => index)

    Promise.all([
      Promise.all(years.map((year) => fetchExpenses(companyId, year))),
      Promise.all(years.map((year) => fetchPayroll(companyId, year))),
    ])
      .then(([allYearsExpenses, allYearsPayroll]) => {
        if (cancelled) return

        const rows = (allYearsExpenses[0] || []).map((entry) => ({
          label: entry.name,
          categoryId: entry.category_id,
          totalsByYear: new Array(years.length).fill(0),
        }))
        const rowByCategoryId = new Map(rows.map((row) => [row.categoryId, row]))

        allYearsExpenses.forEach((yearEntries, yearIndex) => {
          yearEntries.forEach((entry) => {
            if (entry.name === PAYROLL_CATEGORY_NAME) return
            const row = rowByCategoryId.get(entry.category_id)
            if (row) row.totalsByYear[yearIndex] = entry.months.reduce((sum, value) => sum + value, 0)
          })
        })

        const payrollRow = rows.find((row) => row.label === PAYROLL_CATEGORY_NAME)
        if (payrollRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const monthly = computePayrollMonthlyCost(yearRows, years[yearIndex], calendarMode)
            payrollRow.totalsByYear[yearIndex] = monthly.reduce((sum, value) => sum + value, 0)
          })
        }

        setYearSummaryRows(rows)
      })
      .finally(() => {
        if (!cancelled) setYearSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [viewMode, companyId, projectionYears, calendarMode])

  const payrollMonthly = useMemo(
    () => computePayrollMonthlyCost(payrollRows, selectedYear, calendarMode),
    [payrollRows, selectedYear, calendarMode],
  )

  const draftCount = drafts.size

  const handleDraftMonthChange = (categoryId, monthIndex, value, currentMonths, currentHardcoded) => {
    setDrafts((prev) => {
      const next = new Map(prev)
      const base = next.get(categoryId) || { months: [...currentMonths], hardcoded: [...currentHardcoded] }
      const months = [...base.months]
      const hardcoded = [...base.hardcoded]
      months[monthIndex] = value
      // Any month the user types directly here is hardcoded from that point on —
      // it stays marked even after saving, until a future integration overwrites it.
      hardcoded[monthIndex] = true
      next.set(categoryId, { months, hardcoded })
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      for (const [categoryId, draft] of drafts.entries()) {
        // eslint-disable-next-line no-await-in-loop
        await saveExpenseEntry(companyId, categoryId, selectedYear, draft.months, draft.hardcoded)
      }
      await reloadMonthly()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDiscard = () => setDrafts(new Map())

  const grandTotal = new Array(12).fill(0)
  entries.forEach((entry) => {
    const months = entry.name === PAYROLL_CATEGORY_NAME ? payrollMonthly : drafts.get(entry.category_id)?.months || entry.months
    months.forEach((value, index) => {
      grandTotal[index] += Number(value) || 0
    })
  })

  return (
    <div className="panel-surface expenses-view">
      <h3>Expenses</h3>
      <p>Expense categories and budget variance.</p>

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
              {Array.from({ length: projectionYears + 1 }, (_, index) => index).map((yearNumber) => (
                <option key={yearNumber} value={yearNumber}>
                  Year {yearNumber}
                </option>
              ))}
            </select>
          </label>
        )}

        {viewMode === 'monthly' && draftCount > 0 && (
          <span className="expenses-view__draft-actions">
            <button type="button" className="expenses-view__btn" onClick={handleDiscard} disabled={saving}>
              Discard
            </button>
            <button type="button" className="expenses-view__btn expenses-view__btn--primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : `Save ${draftCount} change${draftCount === 1 ? '' : 's'}`}
            </button>
          </span>
        )}
      </div>

      {error && <div className="expenses-view__error">{error}</div>}

      {viewMode === 'yearly' ? (
        yearSummaryLoading ? (
          <div className="expenses-view__status">Loading year summary...</div>
        ) : (
          <YearSummaryTable
            years={Array.from({ length: projectionYears + 1 }, (_, index) => index)}
            rows={yearSummaryRows}
            nameHeader="Category"
            formatValue={(value) => `$${Math.round(value).toLocaleString()}`}
          />
        )
      ) : loading ? (
        <div className="expenses-view__status">Loading expenses...</div>
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
              {entries.map((entry) => {
                const isPayroll = entry.name === PAYROLL_CATEGORY_NAME
                const draft = drafts.get(entry.category_id) || null
                const displayMonths = isPayroll ? payrollMonthly : draft?.months || entry.months
                const displayHardcoded = draft?.hardcoded || entry.hardcoded
                const rowTotal = displayMonths.reduce((sum, value) => sum + (Number(value) || 0), 0)

                return (
                  <tr key={entry.category_id} className={isPayroll ? 'expenses-view__row--imported' : ''}>
                    <td className="sticky-col">
                      {entry.name}
                      {isPayroll && <span className="expenses-view__imported-tag">imported from Payroll</span>}
                    </td>
                    {displayMonths.map((value, index) =>
                      isPayroll ? (
                        <td key={index} className="num">
                          ${Math.round(value).toLocaleString()}
                        </td>
                      ) : (
                        <td key={index} className="num">
                          <span className="expenses-view__cell">
                            <input
                              type="number"
                              className={`expenses-view__month-input ${draft ? 'is-dirty' : ''} ${
                                displayHardcoded[index] ? 'is-hardcoded' : ''
                              }`}
                              value={value}
                              onChange={(event) => {
                                const next = Number(event.target.value)
                                handleDraftMonthChange(
                                  entry.category_id,
                                  index,
                                  Number.isFinite(next) ? next : 0,
                                  entry.months,
                                  entry.hardcoded,
                                )
                              }}
                            />
                            {displayHardcoded[index] && (
                              <span className="expenses-view__hardcoded-mark" title="Hardcoded value — not imported from another module">
                                *
                              </span>
                            )}
                          </span>
                        </td>
                      ),
                    )}
                    <td className="num">${Math.round(rowTotal).toLocaleString()}</td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="expenses-view__total-row">
                <td className="sticky-col">Total</td>
                {grandTotal.map((value, index) => (
                  <td key={index} className="num">
                    ${Math.round(value).toLocaleString()}
                  </td>
                ))}
                <td className="num">${Math.round(grandTotal.reduce((sum, value) => sum + value, 0)).toLocaleString()}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default ExpensesView
