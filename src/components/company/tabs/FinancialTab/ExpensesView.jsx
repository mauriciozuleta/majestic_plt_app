import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchExpenses, saveExpenseEntry } from '../../../../services/expenses'
import { fetchPayroll } from '../../../../services/payroll'
import { fetchSettings } from '../../../../services/settings'
import { fetchExchangeRate } from '../../../../services/exchangeRate'
import { US_BENEFITS, computeFullEmployerCost } from '../../../../services/usBenefits'
import { isUsaLocation } from '../../../../services/usPayrollTax'
import { COP_PER_USD_FALLBACK, isColombiaLocation } from '../../../../services/colombiaPayrollTax'
import { ANG_PER_USD_FALLBACK, isStMaartenLocation } from '../../../../services/stMaartenPayrollTax'
import { positionMonthlyHeadcount } from '../ManagementTab/PayrollView/monthMath'
import YearSummaryTable from '../../../shared/YearSummaryTable'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import './ExpensesView.css'

const MONTH_LABELS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12']

function formatUsdWhole(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function formatLocalWhole(value, currencyCode) {
  return formatCurrencyValue(value, currencyCode, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}
const PAYROLL_CATEGORY_NAME = 'Payroll'
// Employer-side payroll tax cost (Social Security, Medicare, FUTA, SUTA —
// see services/usBenefits.js/usPayrollTax.js). Pre-tax benefits (Section
// 125 health/dental/vision/HSA/FSA) still correctly shrink this wage base
// when enabled, even though their own employer cost is reported separately
// below. Computed from the same live payroll data as the Payroll row
// above, never manually typed in.
const PAYROLL_TAXES_CATEGORY_NAME = 'Payroll Tax Expense'
// The employer's own share of whichever benefits are enabled in Settings >
// Tax Structure > United States > Benefits — a separate row from payroll
// tax, even though both are driven by the same enabled-benefits setting.
const EMPLOYEE_BENEFITS_CATEGORY_NAME = 'Employee Benefits'
const COMPUTED_CATEGORY_NAMES = new Set([PAYROLL_CATEGORY_NAME, PAYROLL_TAXES_CATEGORY_NAME, EMPLOYEE_BENEFITS_CATEGORY_NAME])

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

function computePayrollTaxesMonthlyCost(payrollRows, year, calendarMode, enabledBenefitKeys) {
  const totals = new Array(12).fill(0)
  // US payroll tax (Social Security, Medicare, FUTA, SUTA) only applies to
  // positions actually located in the USA — not every position in the
  // payroll, since this is a US-specific structure.
  payrollRows.filter((row) => isUsaLocation(row.location)).forEach((row) => {
    const months = positionMonthlyHeadcount(row.employees || [], year, calendarMode)
    const annualTaxPerSeat = computeFullEmployerCost(row.year_salary, enabledBenefitKeys).payrollTax.total
    months.forEach((headcount, index) => {
      totals[index] += Math.round((annualTaxPerSeat * headcount) / 12)
    })
  })
  return totals
}

function computeEmployeeBenefitsMonthlyCost(payrollRows, year, calendarMode, enabledBenefitKeys) {
  const totals = new Array(12).fill(0)
  // Same USA-only scoping as payroll tax — these benefits (401k, Section
  // 125 health/dental/vision, etc.) are a US-specific catalog.
  payrollRows.filter((row) => isUsaLocation(row.location)).forEach((row) => {
    const months = positionMonthlyHeadcount(row.employees || [], year, calendarMode)
    const annualBenefitsCostPerSeat = computeFullEmployerCost(row.year_salary, enabledBenefitKeys).benefitsEmployerCost
    months.forEach((headcount, index) => {
      totals[index] += Math.round((annualBenefitsCostPerSeat * headcount) / 12)
    })
  })
  return totals
}

function ExpensesView() {
  const { companyId } = useParams()
  const [calendarMode, setCalendarMode] = useState('real')
  const [projectionYears, setProjectionYears] = useState(5)
  const [enabledBenefitKeys, setEnabledBenefitKeys] = useState([])
  const [viewMode, setViewMode] = useState('monthly')
  const [selectedYear, setSelectedYear] = useState(1)
  const [entries, setEntries] = useState([])
  const [payrollRows, setPayrollRows] = useState([])
  const [drafts, setDrafts] = useState(() => new Map())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [yearSummaryRows, setYearSummaryRows] = useState([])
  const [yearSummaryLoading, setYearSummaryLoading] = useState(false)
  const [colombiaCopPerUsd, setColombiaCopPerUsd] = useState(COP_PER_USD_FALLBACK)
  const [stMaartenAngPerUsd, setStMaartenAngPerUsd] = useState(ANG_PER_USD_FALLBACK)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setCalendarMode(settings.calendar_mode ?? 'real')
        setProjectionYears(Math.max(5, Math.min(10, Number(settings.projection_years ?? 5))))
        setEnabledBenefitKeys(Array.isArray(settings.enabled_benefits) ? settings.enabled_benefits : [])
        // Colombia's calculator uses a user-locked "projected" rate (not the
        // live one) so its numbers stay stable — mirror that same rate here
        // so this row's COP figure matches what the Colombia settings panel
        // itself would show, rather than drifting off a live quote.
        if (settings.colombia_projected_cop_per_usd) setColombiaCopPerUsd(settings.colombia_projected_cop_per_usd)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchExchangeRate('ANG', 'USD')
      .then((result) => {
        if (!cancelled && result?.rate > 0) setStMaartenAngPerUsd(1 / result.rate)
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
    const years = Array.from({ length: projectionYears }, (_, index) => index + 1)

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
            if (COMPUTED_CATEGORY_NAMES.has(entry.name)) return
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

        const payrollTaxesRow = rows.find((row) => row.label === PAYROLL_TAXES_CATEGORY_NAME)
        if (payrollTaxesRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const monthly = computePayrollTaxesMonthlyCost(yearRows, years[yearIndex], calendarMode, enabledBenefitKeys)
            payrollTaxesRow.totalsByYear[yearIndex] = monthly.reduce((sum, value) => sum + value, 0)
          })
        }

        const employeeBenefitsRow = rows.find((row) => row.label === EMPLOYEE_BENEFITS_CATEGORY_NAME)
        if (employeeBenefitsRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const monthly = computeEmployeeBenefitsMonthlyCost(yearRows, years[yearIndex], calendarMode, enabledBenefitKeys)
            employeeBenefitsRow.totalsByYear[yearIndex] = monthly.reduce((sum, value) => sum + value, 0)
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
  }, [viewMode, companyId, projectionYears, calendarMode, enabledBenefitKeys])

  const payrollMonthly = useMemo(
    () => computePayrollMonthlyCost(payrollRows, selectedYear, calendarMode),
    [payrollRows, selectedYear, calendarMode],
  )

  // Payroll tax/benefits only apply to USA positions, so the "effective
  // rate" shown next to those rows needs the USA-only payroll total as its
  // denominator too — using the all-location total (below) would dilute the
  // rate with non-US salaries that carry no US payroll tax at all.
  const usaPayrollMonthly = useMemo(
    () => computePayrollMonthlyCost(payrollRows.filter((row) => isUsaLocation(row.location)), selectedYear, calendarMode),
    [payrollRows, selectedYear, calendarMode],
  )

  // Payroll (base salary) spans every country's positions, so unlike the
  // USA-only tax/benefits rows above, its local-currency subtitle needs a
  // per-country breakdown of the same combined total, not a single rate.
  const colombiaPayrollMonthly = useMemo(
    () => computePayrollMonthlyCost(payrollRows.filter((row) => isColombiaLocation(row.location)), selectedYear, calendarMode),
    [payrollRows, selectedYear, calendarMode],
  )
  const stMaartenPayrollMonthly = useMemo(
    () => computePayrollMonthlyCost(payrollRows.filter((row) => isStMaartenLocation(row.location)), selectedYear, calendarMode),
    [payrollRows, selectedYear, calendarMode],
  )

  const payrollTaxesMonthly = useMemo(
    () => computePayrollTaxesMonthlyCost(payrollRows, selectedYear, calendarMode, enabledBenefitKeys),
    [payrollRows, selectedYear, calendarMode, enabledBenefitKeys],
  )

  const employeeBenefitsMonthly = useMemo(
    () => computeEmployeeBenefitsMonthlyCost(payrollRows, selectedYear, calendarMode, enabledBenefitKeys),
    [payrollRows, selectedYear, calendarMode, enabledBenefitKeys],
  )

  const computedMonthsByCategory = {
    [PAYROLL_CATEGORY_NAME]: payrollMonthly,
    [PAYROLL_TAXES_CATEGORY_NAME]: payrollTaxesMonthly,
    [EMPLOYEE_BENEFITS_CATEGORY_NAME]: employeeBenefitsMonthly,
  }

  // The blended rate actually driving each computed row this year — shown
  // inline so the row isn't a black box. Payroll tax varies per position
  // (the Additional Medicare surcharge only kicks in over $200,000), so
  // it's derived from the real aggregate dollars; the benefits rate is a
  // fixed sum of whichever benefits are enabled, so it's read directly
  // from the catalog rather than back-computed (exact either way, but
  // avoids compounding any rounding from the monthly aggregation).
  const usaPayrollTotalForYear = usaPayrollMonthly.reduce((sum, value) => sum + value, 0)
  const payrollTaxesTotalForYear = payrollTaxesMonthly.reduce((sum, value) => sum + value, 0)
  const effectivePayrollTaxRate = usaPayrollTotalForYear > 0 ? (payrollTaxesTotalForYear / usaPayrollTotalForYear) * 100 : 0
  const enabledBenefitDetails = US_BENEFITS.filter((benefit) => enabledBenefitKeys.includes(benefit.key))
  const totalBenefitsEmployerRate = enabledBenefitDetails.reduce((sum, benefit) => sum + benefit.employerPct, 0) * 100

  // Below-the-value subtitle for the Payroll row only — the only row whose
  // combined USD figure actually spans more than one country's currency
  // right now (Payroll Tax Expense/Employee Benefits are USA-only so far).
  const payrollLocalCurrencyParts = (monthlyColombia, monthlyStMaarten) => {
    const parts = []
    if (monthlyColombia > 0) parts.push(formatLocalWhole(monthlyColombia * colombiaCopPerUsd, 'COP'))
    if (monthlyStMaarten > 0) parts.push(formatLocalWhole(monthlyStMaarten * stMaartenAngPerUsd, 'ANG'))
    return parts
  }
  const colombiaPayrollTotal = colombiaPayrollMonthly.reduce((sum, value) => sum + value, 0)
  const stMaartenPayrollTotal = stMaartenPayrollMonthly.reduce((sum, value) => sum + value, 0)

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
    const months = computedMonthsByCategory[entry.name] || drafts.get(entry.category_id)?.months || entry.months
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
              {Array.from({ length: projectionYears }, (_, index) => index + 1).map((yearNumber) => (
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
            years={Array.from({ length: projectionYears }, (_, index) => index + 1)}
            rows={yearSummaryRows}
            nameHeader="Category"
            formatValue={formatUsdWhole}
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
                const isPayrollTaxes = entry.name === PAYROLL_TAXES_CATEGORY_NAME
                const isEmployeeBenefits = entry.name === EMPLOYEE_BENEFITS_CATEGORY_NAME
                const isComputed = isPayroll || isPayrollTaxes || isEmployeeBenefits
                const draft = drafts.get(entry.category_id) || null
                const displayMonths = computedMonthsByCategory[entry.name] || draft?.months || entry.months
                const displayHardcoded = draft?.hardcoded || entry.hardcoded
                const rowTotal = displayMonths.reduce((sum, value) => sum + (Number(value) || 0), 0)

                return (
                  <tr key={entry.category_id} className={isComputed ? 'expenses-view__row--imported' : ''}>
                    <td className="sticky-col">
                      {entry.name}
                      {isPayroll && <span className="expenses-view__imported-tag">imported from Payroll</span>}
                      {isPayrollTaxes && (
                        <span
                          className="expenses-view__imported-tag"
                          title="Social Security 6.2% + Medicare 1.45% (+0.9% for salaries over $200,000) + FUTA 0.6% + SUTA 1.75%, per position — see Settings > Tax Structure > United States > Payroll taxes/charges"
                        >
                          computed from Payroll ({effectivePayrollTaxRate.toFixed(2)}%)
                        </span>
                      )}
                      {isEmployeeBenefits && (
                        <span
                          className="expenses-view__imported-tag"
                          title={
                            enabledBenefitDetails.length > 0
                              ? enabledBenefitDetails
                                  .map((benefit) => `${benefit.label} ${(benefit.employerPct * 100).toFixed(2)}%`)
                                  .join(', ') + ' — see Settings > Tax Structure > United States > Benefits'
                              : 'No benefits enabled — see Settings > Tax Structure > United States > Benefits'
                          }
                        >
                          computed from Payroll ({totalBenefitsEmployerRate.toFixed(2)}%)
                        </span>
                      )}
                    </td>
                    {displayMonths.map((value, index) =>
                      isComputed ? (
                        <td key={index} className="num">
                          {formatUsdWhole(value)}
                          {isPayroll &&
                            payrollLocalCurrencyParts(colombiaPayrollMonthly[index], stMaartenPayrollMonthly[index]).map(
                              (part) => (
                                <span key={part} className="expenses-view__local-currency">
                                  {part}
                                </span>
                              ),
                            )}
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
                    <td className="num">
                      {formatUsdWhole(rowTotal)}
                      {isPayroll &&
                        payrollLocalCurrencyParts(colombiaPayrollTotal, stMaartenPayrollTotal).map((part) => (
                          <span key={part} className="expenses-view__local-currency">
                            {part}
                          </span>
                        ))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="expenses-view__total-row">
                <td className="sticky-col">Total</td>
                {grandTotal.map((value, index) => (
                  <td key={index} className="num">
                    {formatUsdWhole(value)}
                  </td>
                ))}
                <td className="num">{formatUsdWhole(grandTotal.reduce((sum, value) => sum + value, 0))}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default ExpensesView
