import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import { fetchExpenseCategoryExclusions, fetchExpenses } from '../../../../services/expenses'
import { fetchPayroll } from '../../../../services/payroll'
import { fetchSettings } from '../../../../services/settings'
import { fetchExchangeRate } from '../../../../services/exchangeRate'
import { fetchCommercialCountries } from '../../../../services/commercialStructure'
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

function ExpensesView() {
  const { companyId } = useParams()
  const companies = useAppStore((state) => state.companies)
  const [calendarMode, setCalendarMode] = useState('real')
  const [projectionYears, setProjectionYears] = useState(5)
  const [enabledBenefitKeys, setEnabledBenefitKeys] = useState([])
  const [viewMode, setViewMode] = useState('monthly')
  const [selectedYear, setSelectedYear] = useState(1)
  const [entries, setEntries] = useState([])
  const [payrollRows, setPayrollRows] = useState([])
  const [opsExpenseEntries, setOpsExpenseEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [yearSummaryRows, setYearSummaryRows] = useState([])
  const [yearSummaryLoading, setYearSummaryLoading] = useState(false)
  const [realStartDate, setRealStartDate] = useState('')
  const [colombiaCopPerUsd, setColombiaCopPerUsd] = useState(COP_PER_USD_FALLBACK)
  const [stMaartenAngPerUsd, setStMaartenAngPerUsd] = useState(ANG_PER_USD_FALLBACK)
  const [excludedCategoryIds, setExcludedCategoryIds] = useState(() => new Set())

  // A category is hidden from this company's Expenses if it's been
  // unchecked (Settings > Expenses settings) for every commercial-structure
  // country row whose country code matches THIS company's own home country
  // (Company.country_code) — regardless of which company actually owns
  // that row in the commercial structure. That's necessary because, after
  // splitting payroll into per-country companies, a subsidiary (e.g.
  // FRESH24-Colombia) has no commercial-structure rows of its own; the
  // "Colombia" row a user unchecks in Settings still lives under the
  // parent (FRESH24), so matching by row ownership would never apply the
  // setting to the subsidiary at all. A company whose country has no
  // matching row anywhere has nothing to compare against, so nothing gets
  // hidden for it.
  useEffect(() => {
    if (!companyId || companies.length === 0) return undefined
    const currentCompany = companies.find((company) => company.id === companyId)
    const targetCountryCode = (currentCompany?.countryCode || '').trim().toUpperCase()
    if (!targetCountryCode) {
      setExcludedCategoryIds(new Set())
      return undefined
    }

    let cancelled = false

    Promise.all([
      fetchExpenseCategoryExclusions(),
      Promise.all(companies.map((company) => fetchCommercialCountries(company.id).catch(() => []))),
    ])
      .then(([exclusions, perCompanyCountries]) => {
        if (cancelled) return
        const matchingCountries = perCompanyCountries
          .flat()
          .filter((country) => (country.country_code || '').trim().toUpperCase() === targetCountryCode)
        if (matchingCountries.length === 0) {
          setExcludedCategoryIds(new Set())
          return
        }
        const countryIds = new Set(matchingCountries.map((country) => country.id))
        const excludedByCategoryId = new Map()
        exclusions.forEach(({ category_id: categoryId, country_id: countryId }) => {
          if (!countryIds.has(countryId)) return
          if (!excludedByCategoryId.has(categoryId)) excludedByCategoryId.set(categoryId, new Set())
          excludedByCategoryId.get(categoryId).add(countryId)
        })
        const fullyExcluded = new Set(
          Array.from(excludedByCategoryId.entries())
            .filter(([, excludedCountryIds]) => excludedCountryIds.size >= countryIds.size)
            .map(([categoryId]) => categoryId),
        )
        setExcludedCategoryIds(fullyExcluded)
      })
      .catch(() => {
        if (!cancelled) setExcludedCategoryIds(new Set())
      })

    return () => {
      cancelled = true
    }
  }, [companyId, companies])

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
        if (!cancelled) setOpsExpenseEntries(allEntries.filter((entry) => entry.category === 'expenses'))
      })
      .catch(() => {
        if (!cancelled) setOpsExpenseEntries([])
      })
    return () => {
      cancelled = true
    }
  }, [companyId])

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
          .filter((entry) => !excludedCategoryIds.has(entry.category_id))
          .map((entry) => ({
            label: entry.name,
            categoryId: entry.category_id,
            totalsByYear: new Array(years.length).fill(0),
          }))
        const rowByCategoryId = new Map(rows.map((row) => [row.categoryId, row]))

        allYearsExpenses.forEach((yearEntries, yearIndex) => {
          yearEntries.forEach((entry) => {
            if (COMPUTED_CATEGORY_NAMES.has(entry.name)) return
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

        setYearSummaryRows(rows)
      })
      .finally(() => {
        if (!cancelled) setYearSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [viewMode, companyId, projectionYears, calendarMode, enabledBenefitKeys, excludedCategoryIds, opsByYearAndCategory])

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

  const visibleEntries = entries.filter((entry) => !excludedCategoryIds.has(entry.category_id))

  const grandTotal = new Array(12).fill(0)
  visibleEntries.forEach((entry) => {
    const months = computedMonthsByCategory[entry.name] || entry.months
    const opsForCategory = opsMonthlyByCategoryName[entry.name]
    months.forEach((value, index) => {
      const opsValue = opsForCategory?.hasEntry[index] ? opsForCategory.totals[index] : null
      grandTotal[index] += opsValue !== null ? opsValue : Number(value) || 0
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
                const isComputed = isPayroll || isPayrollTaxes || isEmployeeBenefits
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
                      : undefined

                return (
                  <tr key={entry.category_id} className={isComputed ? 'expenses-view__row--imported' : ''}>
                    <td className="sticky-col" title={categoryTitle}>
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
    </div>
  )
}

export default ExpensesView
