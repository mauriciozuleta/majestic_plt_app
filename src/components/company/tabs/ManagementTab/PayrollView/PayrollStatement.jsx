import { useEffect, useMemo, useState } from 'react'
import { fetchSettings } from '../../../../../services/settings'
import { usePayrollCurrencyRates } from '../../../../../hooks/usePayrollCurrencyRates'
import { useAppStore } from '../../../../../store/useAppStore'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { SMMLV_COP_DEFAULT, UVT_COP_DEFAULT } from '../../../../../services/colombiaPayrollTax'
import {
  aggregatePeriodsForGroup,
  buildPayPeriods,
  computeAnnualBreakdown,
  flattenEmployees,
  getChecksPerYear,
} from './payrollDisbursement'
import './PayrollStatement.css'

function money(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function sumColumn(periods, key) {
  return periods.reduce((sum, period) => sum + period[key], 0)
}

function sumItemColumn(periods, itemsKey, itemIndex) {
  return periods.reduce((sum, period) => sum + period[itemsKey][itemIndex].amount, 0)
}

// A fast-glance total for each of the table's major categories, so the
// numbers below don't need to be scanned/summed by eye. Green values match
// the existing "Net Pay" row treatment (--accent-teal-text) already used
// further down this same table.
function SummaryCards({ periods, employerBenefitsLabels }) {
  const totalGross = sumColumn(periods, 'gross')
  const totalNet = sumColumn(periods, 'net')
  const totalEmployerTax = sumColumn(periods, 'employerTaxTotal')
  const totalEmployerBenefits = sumColumn(periods, 'employerBenefitsTotal')
  const totalCash = periods.reduce((sum, period) => sum + period.gross + period.employerTotal, 0)

  return (
    <div className="payroll-statement__cards">
      <div className="payroll-statement__card">
        <div className="payroll-statement__card-label">Total Gross Pay</div>
        <div className="payroll-statement__card-value">{money(totalGross)}</div>
      </div>
      <div className="payroll-statement__card">
        <div className="payroll-statement__card-label">Total Net Pay</div>
        <div className="payroll-statement__card-value">{money(totalNet)}</div>
      </div>
      <div className="payroll-statement__card">
        <div className="payroll-statement__card-label">Employer Mandatory Contributions</div>
        <div className="payroll-statement__card-value">{money(totalEmployerTax)}</div>
      </div>
      {employerBenefitsLabels.length > 0 && (
        <div className="payroll-statement__card">
          <div className="payroll-statement__card-label">Employer Benefits Contributions</div>
          <div className="payroll-statement__card-value">{money(totalEmployerBenefits)}</div>
        </div>
      )}
      <div className="payroll-statement__card">
        <div className="payroll-statement__card-label">Total Cash Required</div>
        <div className="payroll-statement__card-value">{money(totalCash)}</div>
      </div>
    </div>
  )
}

// Row order and grouping mirror Financial > Expenses' three payroll
// categories: Gross Pay ties to the "Payroll" row, Employer Mandatory
// Contributions to "Payroll Tax Expense", and Employer Benefits to
// "Employee Benefits" — same underlying math (computeFullEmployerCost /
// computeFullEmployeeWithholding), just sliced per pay period here instead
// of per calendar month.
function ItemizedTable({ title, payPeriods, periods }) {
  const employeeLabels = periods[0]?.employeeItems.map((item) => item.label) ?? []
  const employerTaxLabels = periods[0]?.employerTaxItems.map((item) => item.label) ?? []
  const employerBenefitsLabels = periods[0]?.employerBenefitsItems.map((item) => item.label) ?? []
  const totalCashRequired = periods.map((period) => period.gross + period.employerTotal)

  return (
    <div className="payroll-statement__section">
      {title && <h4 className="payroll-statement__section-title">{title}</h4>}
      <SummaryCards periods={periods} employerBenefitsLabels={employerBenefitsLabels} />
      <div className="payroll-statement__scroll">
        <table className="payroll-statement__table">
          <thead>
            <tr>
              <th>Line Item</th>
              {payPeriods.map((period) => (
                <th key={period.index} className="num">
                  {period.label}
                </th>
              ))}
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="payroll-statement__row--gross">
              <td>Gross Pay</td>
              {periods.map((period, index) => (
                <td key={index} className="num">
                  {money(period.gross)}
                </td>
              ))}
              <td className="num">{money(sumColumn(periods, 'gross'))}</td>
            </tr>

            {employeeLabels.length > 0 && (
              <tr className="payroll-statement__row--group-header">
                <td colSpan={payPeriods.length + 2}>Employee Deductions</td>
              </tr>
            )}
            {employeeLabels.map((label, itemIndex) => (
              <tr key={label}>
                <td>{label}</td>
                {periods.map((period, index) => (
                  <td key={index} className="num">
                    {money(period.employeeItems[itemIndex].amount)}
                  </td>
                ))}
                <td className="num">{money(sumItemColumn(periods, 'employeeItems', itemIndex))}</td>
              </tr>
            ))}
            <tr className="payroll-statement__row--subtotal">
              <td>Total Employee Deductions</td>
              {periods.map((period, index) => (
                <td key={index} className="num">
                  {money(period.employeeTotalWithheld)}
                </td>
              ))}
              <td className="num">{money(sumColumn(periods, 'employeeTotalWithheld'))}</td>
            </tr>

            <tr className="payroll-statement__row--net">
              <td>Net Pay (Direct Deposit)</td>
              {periods.map((period, index) => (
                <td key={index} className="num">
                  {money(period.net)}
                </td>
              ))}
              <td className="num">{money(sumColumn(periods, 'net'))}</td>
            </tr>

            {employerTaxLabels.length > 0 && (
              <tr className="payroll-statement__row--group-header">
                <td colSpan={payPeriods.length + 2}>Employer Mandatory Contributions</td>
              </tr>
            )}
            {employerTaxLabels.map((label, itemIndex) => (
              <tr key={label}>
                <td>{label}</td>
                {periods.map((period, index) => (
                  <td key={index} className="num">
                    {money(period.employerTaxItems[itemIndex].amount)}
                  </td>
                ))}
                <td className="num">{money(sumItemColumn(periods, 'employerTaxItems', itemIndex))}</td>
              </tr>
            ))}
            <tr className="payroll-statement__row--subtotal">
              <td>Total Employer Mandatory Contributions</td>
              {periods.map((period, index) => (
                <td key={index} className="num">
                  {money(period.employerTaxTotal)}
                </td>
              ))}
              <td className="num">{money(sumColumn(periods, 'employerTaxTotal'))}</td>
            </tr>

            {employerBenefitsLabels.length > 0 && (
              <>
                <tr className="payroll-statement__row--group-header">
                  <td colSpan={payPeriods.length + 2}>Employer Benefits</td>
                </tr>
                {employerBenefitsLabels.map((label, itemIndex) => (
                  <tr key={label}>
                    <td>{label}</td>
                    {periods.map((period, index) => (
                      <td key={index} className="num">
                        {money(period.employerBenefitsItems[itemIndex].amount)}
                      </td>
                    ))}
                    <td className="num">{money(sumItemColumn(periods, 'employerBenefitsItems', itemIndex))}</td>
                  </tr>
                ))}
                <tr className="payroll-statement__row--subtotal">
                  <td>Total Employer Benefits</td>
                  {periods.map((period, index) => (
                    <td key={index} className="num">
                      {money(period.employerBenefitsTotal)}
                    </td>
                  ))}
                  <td className="num">{money(sumColumn(periods, 'employerBenefitsTotal'))}</td>
                </tr>
              </>
            )}

            <tr className="payroll-statement__row--total">
              <td>Total Cash Required</td>
              {totalCashRequired.map((value, index) => (
                <td key={index} className="num">
                  {money(value)}
                </td>
              ))}
              <td className="num">{money(totalCashRequired.reduce((sum, value) => sum + value, 0))}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PayrollStatement({ companyId, rows, selectedYear, calendarMode }) {
  const [mode, setMode] = useState('summary')
  const [payrollScheduleType, setPayrollScheduleType] = useState('monthly')
  const [enabledBenefitKeys, setEnabledBenefitKeys] = useState([])
  const [colombiaSmmlvCop, setColombiaSmmlvCop] = useState(SMMLV_COP_DEFAULT)
  const [colombiaUvtCop, setColombiaUvtCop] = useState(UVT_COP_DEFAULT)
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [selectedMonthIndex, setSelectedMonthIndex] = useState('all')
  const currencyRates = usePayrollCurrencyRates()
  const companyCountryCode = useAppStore((state) => state.companies.find((company) => company.id === companyId)?.countryCode)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setPayrollScheduleType(settings.payroll_schedule_type === 'biweekly' ? 'biweekly' : 'monthly')
        setEnabledBenefitKeys(Array.isArray(settings.enabled_benefits) ? settings.enabled_benefits : [])
        if (settings.colombia_smmlv_cop) setColombiaSmmlvCop(settings.colombia_smmlv_cop)
        if (settings.colombia_uvt_cop) setColombiaUvtCop(settings.colombia_uvt_cop)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const checksPerYear = getChecksPerYear(payrollScheduleType)
  const payPeriods = useMemo(() => buildPayPeriods(payrollScheduleType, calendarMode), [payrollScheduleType, calendarMode])

  const monthOptions = useMemo(() => {
    const seen = new Map()
    payPeriods.forEach((period) => {
      if (!seen.has(period.monthIndex)) seen.set(period.monthIndex, period.monthLabel)
    })
    return Array.from(seen.entries()).map(([monthIndex, label]) => ({ monthIndex, label }))
  }, [payPeriods])

  // Filters both the Summary and By Employee tables down to just the 1
  // (monthly) or 2 (biweekly) checks that fall in the chosen month, instead
  // of always showing the full year's worth of columns.
  const visiblePayPeriods = useMemo(() => {
    if (selectedMonthIndex === 'all') return payPeriods
    return payPeriods.filter((period) => period.monthIndex === Number(selectedMonthIndex))
  }, [payPeriods, selectedMonthIndex])

  const context = useMemo(
    () => ({
      enabledBenefitKeys,
      checksPerYear,
      colombiaRates: { copPerUsd: currencyRates.copPerUsd, smmlvCop: colombiaSmmlvCop, uvtCop: colombiaUvtCop },
      angPerUsd: currencyRates.angPerUsd,
      companyCountryCode,
    }),
    [enabledBenefitKeys, checksPerYear, currencyRates.copPerUsd, currencyRates.angPerUsd, colombiaSmmlvCop, colombiaUvtCop, companyCountryCode],
  )

  // One breakdown per POSITION, not per employee — every employee on a
  // position shares that position's flat salary, so this avoids redoing the
  // same tax math once per seat. All positions share the same country
  // (the company's own), so this is really "one breakdown per distinct
  // salary" in practice, just keyed by position for simplicity.
  const breakdownByNodeId = useMemo(() => {
    const map = new Map()
    rows.forEach((row) => map.set(row.node_id, computeAnnualBreakdown(row, context)))
    return map
  }, [rows, context])

  const employeeEntries = useMemo(
    () =>
      flattenEmployees(rows).map(({ employee, row }) => ({
        employee,
        row,
        breakdown: breakdownByNodeId.get(row.node_id),
      })),
    [rows, breakdownByNodeId],
  )

  const countryLabel = employeeEntries[0]?.breakdown.country

  const summaryPeriods = useMemo(
    () => aggregatePeriodsForGroup(employeeEntries, visiblePayPeriods, selectedYear, calendarMode, checksPerYear),
    [employeeEntries, visiblePayPeriods, selectedYear, calendarMode, checksPerYear],
  )

  const selectedEntry = employeeEntries.find((entry) => entry.employee.id === selectedEmployeeId) ?? null
  const selectedEmployeePeriods = useMemo(
    () =>
      selectedEntry
        ? aggregatePeriodsForGroup([selectedEntry], visiblePayPeriods, selectedYear, calendarMode, checksPerYear)
        : [],
    [selectedEntry, visiblePayPeriods, selectedYear, calendarMode, checksPerYear],
  )

  return (
    <div className="payroll-statement">
      <div className="payroll-statement__toolbar">
        <div className="payroll-view__view-toggle">
          <button type="button" className={mode === 'summary' ? 'is-active' : ''} onClick={() => setMode('summary')}>
            Summary
          </button>
          <button type="button" className={mode === 'employee' ? 'is-active' : ''} onClick={() => setMode('employee')}>
            By Employee
          </button>
        </div>
        <label className="payroll-statement__month-picker">
          Month
          <select value={selectedMonthIndex} onChange={(event) => setSelectedMonthIndex(event.target.value)}>
            <option value="all">All months</option>
            {monthOptions.map((option) => (
              <option key={option.monthIndex} value={option.monthIndex}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <p className="payroll-statement__schedule-hint">
          {countryLabel ? `${countryLabel} · ` : ''}
          {payrollScheduleType === 'biweekly' ? 'Biweekly' : 'Monthly'} — {checksPerYear} checks/year
        </p>
      </div>

      {employeeEntries.length === 0 ? (
        <div className="payroll-view__status">No employees on the roster for Year {selectedYear}.</div>
      ) : visiblePayPeriods.length === 0 ? (
        <div className="payroll-view__status">No pay periods fall in that month.</div>
      ) : mode === 'summary' ? (
        <ItemizedTable
          title={`All Positions${countryLabel ? ` — ${countryLabel}` : ''}`}
          payPeriods={visiblePayPeriods}
          periods={summaryPeriods}
        />
      ) : (
        <>
          <label className="payroll-statement__employee-picker">
            Employee
            <select value={selectedEmployeeId} onChange={(event) => setSelectedEmployeeId(event.target.value)}>
              <option value="">-- Select an employee --</option>
              {employeeEntries.map(({ employee, row }) => (
                <option key={employee.id} value={employee.id}>
                  {employee.employee_name || 'Unnamed employee'} — {row.office_name}
                </option>
              ))}
            </select>
          </label>

          {selectedEntry && (
            <ItemizedTable
              title={`${selectedEntry.employee.employee_name || 'Unnamed employee'} — ${selectedEntry.row.office_name}`}
              payPeriods={visiblePayPeriods}
              periods={selectedEmployeePeriods}
            />
          )}
        </>
      )}
    </div>
  )
}

export default PayrollStatement
