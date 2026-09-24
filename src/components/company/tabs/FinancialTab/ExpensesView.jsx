import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchExpenses } from '../../../../services/expenses'
import { fetchPayroll } from '../../../../services/payroll'
import { fetchSettings } from '../../../../services/settings'
import { fetchExchangeRate } from '../../../../services/exchangeRate'
import { fetchCommercialOperationEntries } from '../../../../services/commercialOperations'
import { US_BENEFITS, computeFullEmployerCost } from '../../../../services/usBenefits'
import { isUsaLocation } from '../../../../services/usPayrollTax'
import { COP_PER_USD_FALLBACK, isColombiaLocation } from '../../../../services/colombiaPayrollTax'
import { ANG_PER_USD_FALLBACK, isStMaartenLocation } from '../../../../services/stMaartenPayrollTax'
import { positionMonthlyHeadcount } from '../ManagementTab/PayrollView/monthMath'
import { isoDateToSimDate } from '../../../shared/SimulationCalendar/simulationCalendarMath'
import { isoDateToAnchoredYearMonth } from '../../../../utils/anchoredProjectionCalendar'
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

// A row's real monthly values: a computed row (Payroll/Payroll Tax/Employee
// Benefits/percent-of-X) uses its computed array instead of entry.months,
// and any month with a real Commercial Operations entry wins over either of
// those — same ops-over-computed-over-manual precedence used everywhere
// else in this view.
function getEffectiveMonths(entry, computedMonthsByCategory, opsMonthlyByCategoryName) {
  const baseMonths = computedMonthsByCategory[entry.name] || entry.months
  const opsForCategory = opsMonthlyByCategoryName[entry.name]
  return baseMonths.map((value, index) => (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : Number(value) || 0))
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
  const [opsExpenseEntries, setOpsExpenseEntries] = useState([])
  const [opsRevenueEntries, setOpsRevenueEntries] = useState([])
  const [opsCosEntries, setOpsCosEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [yearSummaryRows, setYearSummaryRows] = useState([])
  const [yearSummaryLoading, setYearSummaryLoading] = useState(false)
  const [realStartDate, setRealStartDate] = useState('')
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
        setRealStartDate(settings.real_start_date || '')
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

  // Actual expense transactions logged in Operations > Commercial Operations
  // ("Add Expense") — matched to a category by the entry's description,
  // which is set from that same category's name when the entry is created.
  // Fetched once per company (not year-scoped) since the endpoint returns
  // every entry regardless of date; bucketing by year/month happens below.
  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    fetchCommercialOperationEntries(companyId)
      .then((allEntries) => {
        if (cancelled) return
        setOpsExpenseEntries(allEntries.filter((entry) => entry.category === 'expenses'))
        setOpsRevenueEntries(allEntries.filter((entry) => entry.category === 'revenue'))
        setOpsCosEntries(allEntries.filter((entry) => entry.category === 'cos'))
      })
      .catch(() => {
        if (!cancelled) {
          setOpsExpenseEntries([])
          setOpsRevenueEntries([])
          setOpsCosEntries([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [companyId])

  // Sums every entry's amount into a {year: [12 monthly totals]} map — used
  // for Revenue/COGS totals, which (unlike expense categories) don't need
  // to be split out by name the way opsByYearAndCategory below is.
  const bucketOpsEntriesByYear = useCallback(
    (opsEntries, filterFn) => {
      const map = {}
      if (calendarMode === 'real' && !realStartDate) return map
      opsEntries.forEach((entry) => {
        if (filterFn && !filterFn(entry)) return
        let yearMonth
        try {
          yearMonth =
            calendarMode === 'simulation' ? isoDateToSimDate(entry.entry_date) : isoDateToAnchoredYearMonth(realStartDate, entry.entry_date)
        } catch {
          return
        }
        if (!map[yearMonth.year]) map[yearMonth.year] = new Array(12).fill(0)
        map[yearMonth.year][yearMonth.month - 1] += entry.amount
      })
      return map
    },
    [calendarMode, realStartDate],
  )

  // Gross Revenue is every revenue entry at face value; Net Revenue
  // subtracts discount entries (is_discount) from that same total — see
  // gl_engine.py's revenue_code choice ('4900' contra-revenue vs '4000')
  // for the same distinction on the accounting side. "Net Profit" (the
  // other %-of-X base) is derived further below, from Net Revenue minus
  // COGS minus every non-percent expense — never from Gross Revenue.
  const grossRevenueByYear = useMemo(() => bucketOpsEntriesByYear(opsRevenueEntries), [bucketOpsEntriesByYear, opsRevenueEntries])
  const discountByYear = useMemo(
    () => bucketOpsEntriesByYear(opsRevenueEntries, (entry) => entry.is_discount),
    [bucketOpsEntriesByYear, opsRevenueEntries],
  )
  const cogsByYear = useMemo(() => bucketOpsEntriesByYear(opsCosEntries), [bucketOpsEntriesByYear, opsCosEntries])

  // Per projection year and category name, which months have an actual
  // Commercial Operations expense posted, and their summed amount.
  // isoDateToSimDate turns a real ISO date into a projection-year number in
  // simulation mode; real mode has its own anchor now (Settings' persisted
  // real_start_date), via the same day-count convention generalized in
  // anchoredProjectionCalendar.js — so this only stays empty if real mode
  // has no anchor to compute from yet (a portfolio that's never loaded
  // settings), in which case the tab falls back to whatever was typed in
  // manually, same as before.
  const opsByYearAndCategory = useMemo(() => {
    const map = {}
    if (calendarMode === 'real' && !realStartDate) return map
    opsExpenseEntries.forEach((entry) => {
      let yearMonth
      try {
        yearMonth =
          calendarMode === 'simulation' ? isoDateToSimDate(entry.entry_date) : isoDateToAnchoredYearMonth(realStartDate, entry.entry_date)
      } catch {
        return
      }
      if (!entry.description) return
      if (!map[yearMonth.year]) map[yearMonth.year] = {}
      const yearMap = map[yearMonth.year]
      if (!yearMap[entry.description]) {
        yearMap[entry.description] = { totals: new Array(12).fill(0), hasEntry: new Array(12).fill(false) }
      }
      const bucket = yearMap[entry.description]
      bucket.totals[yearMonth.month - 1] += entry.amount
      bucket.hasEntry[yearMonth.month - 1] = true
    })
    return map
  }, [opsExpenseEntries, calendarMode, realStartDate])

  const opsMonthlyByCategoryName = opsByYearAndCategory[selectedYear] || {}

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

        const rows = (allYearsExpenses[0] || [])
          .filter((entry) => !entry.excluded)
          .map((entry) => ({
            label: entry.name,
            categoryId: entry.category_id,
            totalsByYear: new Array(years.length).fill(0),
            percentOfEnabled: entry.percent_of_enabled,
            percentOfMetric: entry.percent_of_metric,
            percentValue: entry.percent_value,
          }))
        const rowByCategoryId = new Map(rows.map((row) => [row.categoryId, row]))

        allYearsExpenses.forEach((yearEntries, yearIndex) => {
          yearEntries.forEach((entry) => {
            if (COMPUTED_CATEGORY_NAMES.has(entry.name) || entry.percent_of_enabled) return
            const row = rowByCategoryId.get(entry.category_id)
            if (!row) return
            const opsForCategory = opsByYearAndCategory[years[yearIndex]]?.[entry.name]
            row.totalsByYear[yearIndex] = entry.months.reduce(
              (sum, value, index) => sum + (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : value),
              0,
            )
          })
        })

        // The three computed rows prefer Commercial Operations totals over
        // the live payroll calc for any month that already has a Payroll
        // Schedule (or manually-added) ops entry — same ops-over-manual
        // precedence every other category already uses above — falling
        // back to the live calc only where no ops entry exists yet, so a
        // company that hasn't turned Automatic Schedule on keeps seeing the
        // preview it always has.
        const payrollRow = rows.find((row) => row.label === PAYROLL_CATEGORY_NAME)
        if (payrollRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const computed = computePayrollMonthlyCost(yearRows, years[yearIndex], calendarMode)
            const opsForCategory = opsByYearAndCategory[years[yearIndex]]?.[PAYROLL_CATEGORY_NAME]
            payrollRow.totalsByYear[yearIndex] = computed.reduce(
              (sum, value, index) => sum + (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : value),
              0,
            )
          })
        }

        const payrollTaxesRow = rows.find((row) => row.label === PAYROLL_TAXES_CATEGORY_NAME)
        if (payrollTaxesRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const computed = computePayrollTaxesMonthlyCost(yearRows, years[yearIndex], calendarMode, enabledBenefitKeys)
            const opsForCategory = opsByYearAndCategory[years[yearIndex]]?.[PAYROLL_TAXES_CATEGORY_NAME]
            payrollTaxesRow.totalsByYear[yearIndex] = computed.reduce(
              (sum, value, index) => sum + (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : value),
              0,
            )
          })
        }

        const employeeBenefitsRow = rows.find((row) => row.label === EMPLOYEE_BENEFITS_CATEGORY_NAME)
        if (employeeBenefitsRow) {
          allYearsPayroll.forEach((yearRows, yearIndex) => {
            const computed = computeEmployeeBenefitsMonthlyCost(yearRows, years[yearIndex], calendarMode, enabledBenefitKeys)
            const opsForCategory = opsByYearAndCategory[years[yearIndex]]?.[EMPLOYEE_BENEFITS_CATEGORY_NAME]
            employeeBenefitsRow.totalsByYear[yearIndex] = computed.reduce(
              (sum, value, index) => sum + (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : value),
              0,
            )
          })
        }

        // Percent-of-X rows: computed per year from that year's Gross/Net
        // Revenue, COGS, and every fixed (non-percent) row's own yearly
        // total — the same "Net Profit before percent expenses" logic the
        // monthly view uses above, just summed across the year's 12 months
        // instead of computed month-by-month.
        years.forEach((year, yearIndex) => {
          const grossRevenueTotal = (grossRevenueByYear[year] || new Array(12).fill(0)).reduce((sum, value) => sum + value, 0)
          const discountTotal = (discountByYear[year] || new Array(12).fill(0)).reduce((sum, value) => sum + value, 0)
          const cogsTotal = (cogsByYear[year] || new Array(12).fill(0)).reduce((sum, value) => sum + value, 0)
          const netRevenueTotal = grossRevenueTotal - discountTotal
          const fixedExpensesTotal = rows
            .filter((row) => !row.percentOfEnabled)
            .reduce((sum, row) => sum + row.totalsByYear[yearIndex], 0)
          const netProfitBeforePercentTotal = netRevenueTotal - cogsTotal - fixedExpensesTotal

          rows
            .filter((row) => row.percentOfEnabled)
            .forEach((row) => {
              const rate = (row.percentValue || 0) / 100
              const base = row.percentOfMetric === 'gross_revenue' ? grossRevenueTotal : netProfitBeforePercentTotal
              row.totalsByYear[yearIndex] = base * rate
            })
        })

        setYearSummaryRows(rows)
      })
      .finally(() => {
        if (!cancelled) setYearSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [
    viewMode,
    companyId,
    projectionYears,
    calendarMode,
    enabledBenefitKeys,
    opsByYearAndCategory,
    grossRevenueByYear,
    discountByYear,
    cogsByYear,
  ])

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

  // A percent-of-X category's own monthly value never comes from entry.months
  // (nothing is ever typed into it) or from an ops entry (it's disabled in
  // Add Expense's dropdown) — it's `percent_value`% of either Gross Revenue
  // or "Net Profit before percent expenses", computed below and then folded
  // into computedMonthsByCategory just like Payroll/etc. are, so every row
  // downstream (grand total, Year Summary) treats it identically to any
  // other computed row.
  const grossRevenueMonthly = grossRevenueByYear[selectedYear] || new Array(12).fill(0)
  const discountMonthly = discountByYear[selectedYear] || new Array(12).fill(0)
  const cogsMonthly = cogsByYear[selectedYear] || new Array(12).fill(0)
  const netRevenueMonthly = grossRevenueMonthly.map((value, index) => value - discountMonthly[index])

  const visibleEntries = entries.filter((entry) => !entry.excluded)
  const percentEntries = visibleEntries.filter((entry) => entry.percent_of_enabled)
  const fixedEntries = visibleEntries.filter((entry) => !entry.percent_of_enabled)

  // "Net Profit before percent expenses" = Net Revenue - COGS - every fixed
  // (non-percent) expense, INCLUDING Payroll/Payroll Tax/Employee Benefits.
  // Percent categories are deliberately excluded from this base — Net
  // Profit already subtracts every expense, so a category that's itself a
  // percentage of Net Profit can't be part of that subtraction without the
  // calculation depending on its own result.
  const fixedExpensesMonthly = new Array(12).fill(0)
  fixedEntries.forEach((entry) => {
    const months = getEffectiveMonths(entry, computedMonthsByCategory, opsMonthlyByCategoryName)
    months.forEach((value, index) => {
      fixedExpensesMonthly[index] += value
    })
  })
  const netProfitBeforePercentMonthly = netRevenueMonthly.map(
    (value, index) => value - cogsMonthly[index] - fixedExpensesMonthly[index],
  )

  percentEntries.forEach((entry) => {
    const rate = (entry.percent_value || 0) / 100
    const base = entry.percent_of_metric === 'gross_revenue' ? grossRevenueMonthly : netProfitBeforePercentMonthly
    computedMonthsByCategory[entry.name] = base.map((value) => value * rate)
  })

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

  const grandTotal = new Array(12).fill(0)
  visibleEntries.forEach((entry) => {
    const months = getEffectiveMonths(entry, computedMonthsByCategory, opsMonthlyByCategoryName)
    months.forEach((value, index) => {
      grandTotal[index] += value
    })
  })

  return (
    <div className="panel-surface expenses-view">
      <h3>Expenses</h3>

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
                <th
                  className="sticky-col"
                  title="A read-only summary — every value here is fed by Payroll or by Add Expense entries in Operations > Commercial Operations."
                >
                  Category
                </th>
                {MONTH_LABELS.map((label) => (
                  <th key={label} className="num">
                    {label}
                  </th>
                ))}
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {visibleEntries.map((entry) => {
                const isPayroll = entry.name === PAYROLL_CATEGORY_NAME
                const isPayrollTaxes = entry.name === PAYROLL_TAXES_CATEGORY_NAME
                const isEmployeeBenefits = entry.name === EMPLOYEE_BENEFITS_CATEGORY_NAME
                const isPercentOf = entry.percent_of_enabled
                const isPayrollDriven = isPayroll || isPayrollTaxes || isEmployeeBenefits
                const displayMonths = computedMonthsByCategory[entry.name] || entry.months
                // Ops-sourced totals (Payroll Schedule's auto-generated
                // entries, or a manually-added one with a matching
                // description) win over the live payroll calc for these
                // three rows too, same precedence every other category
                // already uses — falling back to the live calc only for a
                // month with no ops entry yet.
                const opsForCategory = opsMonthlyByCategoryName[entry.name]
                const rowTotal = displayMonths.reduce(
                  (sum, value, index) =>
                    sum + (opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : Number(value) || 0),
                  0,
                )
                const percentMetricLabel = entry.percent_of_metric === 'gross_revenue' ? 'Gross Revenue' : 'Net Profit'
                const categoryTitle = isPayroll
                  ? 'Imported from Payroll.'
                  : isPayrollTaxes
                    ? `Computed from Payroll (${effectivePayrollTaxRate.toFixed(2)}%) — Social Security 6.2% + Medicare 1.45% (+0.9% for salaries over $200,000) + FUTA 0.6% + SUTA 1.75%, per position — see Settings > Tax Structure > United States > Payroll taxes/charges`
                    : isEmployeeBenefits
                      ? `Computed from Payroll (${totalBenefitsEmployerRate.toFixed(2)}%) — ${
                          enabledBenefitDetails.length > 0
                            ? enabledBenefitDetails
                                .map((benefit) => `${benefit.label} ${(benefit.employerPct * 100).toFixed(2)}%`)
                                .join(', ') + ' — see Settings > Tax Structure > United States > Benefits'
                            : 'No benefits enabled — see Settings > Tax Structure > United States > Benefits'
                        }`
                      : isPercentOf
                        ? entry.percent_value
                          ? `${entry.percent_value}% of ${percentMetricLabel} — see Settings > Expenses settings`
                          : `% of ${percentMetricLabel} — no rate set for this company yet, see Settings > Expenses settings`
                        : undefined

                const rowClassName = isPayrollDriven
                  ? 'expenses-view__row--imported'
                  : isPercentOf
                    ? 'expenses-view__row--percent'
                    : ''
                // The sticky name cell gets a solid (non-transparent) fill
                // instead of the row's subtle tint — a row-level trait
                // (payroll-driven vs. percent-of) should be obvious at a
                // glance scanning down that one column, not just visible as
                // a faint wash once you're already looking at the row.
                // Ops-sourced isn't included here: it's a per-month cell
                // trait, not a whole-category one, so it stays as the
                // existing per-cell teal instead of coloring the name too.
                const nameClassName = isPayrollDriven
                  ? 'expenses-view__name--imported'
                  : isPercentOf
                    ? 'expenses-view__name--percent'
                    : ''

                return (
                  <tr key={entry.category_id} className={rowClassName}>
                    <td className={`sticky-col ${nameClassName}`} title={categoryTitle}>
                      {entry.name}
                    </td>
                    {displayMonths.map((value, index) =>
                      opsForCategory?.hasEntry[index] ? (
                        <td key={index} className="num expenses-view__cell--ops" title="From Commercial Operations">
                          {formatUsdWhole(opsForCategory.totals[index])}
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

      {viewMode === 'monthly' && !loading && (
        <ul className="expenses-view__legend">
          <li>
            <span className="expenses-view__legend-swatch expenses-view__legend-swatch--imported" />
            Country-specific, computed from Payroll — Payroll, Payroll Tax Expense, Employee Benefits.
          </li>
          <li>
            <span className="expenses-view__legend-swatch expenses-view__legend-swatch--percent" />
            A percentage of Gross Revenue or Net Profit — set in Settings &gt; Expenses settings, never typed in directly.
          </li>
          <li>
            <span className="expenses-view__legend-swatch expenses-view__legend-swatch--ops" />
            From Commercial Operations — an actual Add Expense entry exists for that month.
          </li>
        </ul>
      )}
    </div>
  )
}

export default ExpensesView
