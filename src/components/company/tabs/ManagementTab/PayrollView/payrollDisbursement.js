// Per-paycheck disbursement math for the Payroll Statement view — turns a
// position's flat annual salary into what actually gets wired out each pay
// period: gross pay, the employee's own withholding (taxes + benefit
// deductions), the employer's matching cost (split into mandatory
// contributions vs benefits, mirroring Financial > Expenses' "Payroll Tax
// Expense" and "Employee Benefits" rows), and net take-home. Reuses the
// exact same country tax modules already used by Settings > Tax Structure
// and Expenses, just sliced per pay period instead of per year/month.
//
// Which country's rules apply is the COMPANY's own assigned country
// (Company.country_code, set on the Add Company form — 'US'/'CO'/'MF' for
// the three companies this app actually has) — not each position's own
// free-text `location` string. A company operates in one country, so every
// position/employee in it uses that same set of rules.
//
// There is no per-employee salary field anywhere in this app's data model —
// every employee on a position earns that position's flat year_salary, and
// each is computed independently here (headcount > 1 just means the same
// math runs once per employee on that seat).
import { employeeMonthlyActive } from './monthMath'
import { computeFullEmployeeWithholding, computeFullEmployerCost } from '../../../../../services/usBenefits'
import {
  computeEmployeeWithholding as computeColombiaEmployeeWithholding,
  computeEmployerPayrollTax as computeColombiaEmployerPayrollTax,
  ARL_RISK_CLASSES,
  ARL_DEFAULT_CLASS_KEY,
} from '../../../../../services/colombiaPayrollTax'
import {
  computeEmployeeWithholding as computeStMaartenEmployeeWithholding,
  computeEmployerPayrollTax as computeStMaartenEmployerPayrollTax,
  OV_RATE_DEFAULT,
} from '../../../../../services/stMaartenPayrollTax'

// The reference-country codes this app's companies are actually assigned
// (see Add Company form / CommercialCountry catalog) — 'MF' is "Saint
// Martin (French part)" in that catalog, which is how this app's Sint
// Maarten (Dutch side, SZV) tax structure is reached; there's no separate
// correctly-labeled entry for it in the reference country list.
export const COUNTRY_CODE_LABELS = {
  US: 'United States',
  CO: 'Colombia',
  MF: 'Sint Maarten',
}

export const REAL_MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

const ARL_DEFAULT_RATE = ARL_RISK_CLASSES.find((item) => item.key === ARL_DEFAULT_CLASS_KEY)?.rate ?? 0.00522

export function getChecksPerYear(payrollScheduleType) {
  return payrollScheduleType === 'biweekly' ? 24 : 12
}

/** One entry per pay period in the year — `monthIndex` (0-11) is which
 * calendar month's active/inactive flag governs whether an employee is
 * paid that period (biweekly periods share their month's single flag,
 * since nothing in this app tracks activity more precisely than a month). */
export function buildPayPeriods(payrollScheduleType, calendarMode) {
  const checksPerYear = getChecksPerYear(payrollScheduleType)
  const periodsPerMonth = checksPerYear / 12
  return Array.from({ length: checksPerYear }, (_, index) => {
    const monthIndex = Math.floor(index / periodsPerMonth)
    const monthLabel = calendarMode === 'simulation' ? `Month ${monthIndex + 1}` : REAL_MONTH_NAMES[monthIndex]
    const half = periodsPerMonth > 1 ? (index % periodsPerMonth) + 1 : null
    return { index, monthIndex, monthLabel, label: half ? `${monthLabel} · Check ${half}` : monthLabel }
  })
}

// A uniform shape every country's math gets normalized into, so the view
// layer never has to branch on country — just render whatever items came
// back. `employerTaxItems`/`employerBenefitsItems`/`employeeItems` are
// [{ label, annualAmount }]. Employer cost is split into two groups —
// "mandatory contributions" (Social Security/Medicare/FUTA/SUTA, or each
// country's equivalent) and "benefits" — matching Financial > Expenses'
// separate "Payroll Tax Expense" and "Employee Benefits" rows.
function buildResult(
  country,
  annualSalary,
  employerTaxItems,
  employerTaxTotal,
  employerBenefitsItems,
  employerBenefitsTotal,
  employeeItems,
  employeeTotalWithheld,
  netAnnual,
) {
  return {
    country,
    grossAnnual: annualSalary,
    employerTaxItems,
    employerTaxTotalAnnual: employerTaxTotal,
    employerBenefitsItems,
    employerBenefitsTotalAnnual: employerBenefitsTotal,
    employerTotalAnnual: employerTaxTotal + employerBenefitsTotal,
    employeeItems,
    employeeTotalWithheldAnnual: employeeTotalWithheld,
    netAnnual,
  }
}

/** Full-year breakdown for one employee's position — annual figures only;
 * the view divides by checksPerYear to get a per-check column. Uses the
 * position's flat year_salary, since employees don't carry their own
 * salary field. `context` carries the settings/rates every country's
 * module needs, plus `companyCountryCode` — the one country whose rules
 * apply to every position in this company. */
export function computeAnnualBreakdown(row, context) {
  const annualSalary = Number(row.year_salary) || 0
  const { enabledBenefitKeys, checksPerYear, colombiaRates, angPerUsd, companyCountryCode, usState } = context
  const countryCode = String(companyCountryCode || '').trim().toUpperCase()

  if (countryCode === 'US') {
    const employer = computeFullEmployerCost(annualSalary, enabledBenefitKeys)
    const employee = computeFullEmployeeWithholding(annualSalary, usState || null, checksPerYear, enabledBenefitKeys)
    return buildResult(
      COUNTRY_CODE_LABELS.US,
      annualSalary,
      [
        { label: 'Social Security (Employer)', annualAmount: employer.payrollTax.socialSecurity },
        { label: 'Medicare (Employer)', annualAmount: employer.payrollTax.medicare },
        { label: 'Additional Medicare (Employer)', annualAmount: employer.payrollTax.additionalMedicare },
        { label: 'FUTA', annualAmount: employer.payrollTax.futa },
        { label: 'SUTA', annualAmount: employer.payrollTax.suta },
      ],
      employer.payrollTax.total,
      employer.benefitsBreakdown.map((benefit) => ({ label: benefit.label, annualAmount: benefit.employerAmount })),
      employer.benefitsEmployerCost,
      [
        { label: 'Social Security (Employee)', annualAmount: employee.socialSecurity },
        { label: 'Medicare (Employee)', annualAmount: employee.medicare },
        { label: 'Federal Income Tax', annualAmount: employee.federalTax },
        { label: 'State Income Tax', annualAmount: employee.stateTax },
        ...employee.benefitsBreakdown.map((benefit) => ({ label: `${benefit.label} (Employee)`, annualAmount: benefit.employeeAmount })),
      ],
      employee.totalWithheld + employee.benefitsEmployeeCost,
      employee.netAnnual,
    )
  }

  if (countryCode === 'CO') {
    const copPerUsd = colombiaRates.copPerUsd
    const smmlvCop = colombiaRates.smmlvCop
    const uvtCop = colombiaRates.uvtCop
    const employer = computeColombiaEmployerPayrollTax(annualSalary, copPerUsd, ARL_DEFAULT_RATE, smmlvCop)
    const employee = computeColombiaEmployeeWithholding(annualSalary, copPerUsd, smmlvCop, uvtCop)
    return buildResult(
      COUNTRY_CODE_LABELS.CO,
      annualSalary,
      [
        { label: 'Pensión (Employer)', annualAmount: employer.pension },
        { label: 'Salud (Employer)', annualAmount: employer.salud },
        { label: 'ARL', annualAmount: employer.arl },
        { label: 'Caja de Compensación', annualAmount: employer.caja },
        { label: 'ICBF', annualAmount: employer.icbf },
        { label: 'SENA', annualAmount: employer.sena },
        { label: 'Cesantías', annualAmount: employer.cesantias },
        { label: 'Intereses sobre Cesantías', annualAmount: employer.interesesCesantias },
        { label: 'Prima de Servicios', annualAmount: employer.prima },
      ],
      employer.total,
      // No employee-benefits catalog exists for Colombia in this app today —
      // everything the employer pays here is a mandatory contribution.
      [],
      0,
      [
        { label: 'Pensión (Employee)', annualAmount: employee.pension },
        { label: 'Fondo de Solidaridad Pensional', annualAmount: employee.fsp },
        { label: 'Salud (Employee)', annualAmount: employee.salud },
        { label: 'Retención en la Fuente', annualAmount: employee.withholding },
      ],
      employee.totalWithheld,
      employee.netAnnual,
    )
  }

  if (countryCode === 'MF') {
    const employer = computeStMaartenEmployerPayrollTax(annualSalary, angPerUsd, OV_RATE_DEFAULT)
    const employee = computeStMaartenEmployeeWithholding(annualSalary, angPerUsd)
    return buildResult(
      COUNTRY_CODE_LABELS.MF,
      annualSalary,
      [
        { label: 'AOV (Employer)', annualAmount: employer.aov },
        { label: 'AWW (Employer)', annualAmount: employer.aww },
        { label: 'BVZ (Employer)', annualAmount: employer.bvz },
        { label: 'AVBZ (Employer)', annualAmount: employer.avbz },
        { label: 'ZV', annualAmount: employer.zv },
        { label: 'OV', annualAmount: employer.ov },
      ],
      employer.total,
      // No employee-benefits catalog exists for Sint Maarten in this app
      // today — everything the employer pays here is a mandatory premium.
      [],
      0,
      [
        { label: 'AOV (Employee)', annualAmount: employee.aov },
        { label: 'AWW (Employee)', annualAmount: employee.aww },
        { label: 'BVZ (Employee)', annualAmount: employee.bvz },
        { label: 'AVBZ (Employee)', annualAmount: employee.avbz },
        { label: 'Wage Tax', annualAmount: employee.wageTax },
      ],
      employee.totalWithheld,
      employee.netAnnual,
    )
  }

  // No tax module recognizes this company's country — show gross only
  // rather than silently fabricating a number for an unmodeled country.
  return buildResult('Unrecognized country', annualSalary, [], 0, [], 0, [], 0, annualSalary)
}

/** Flattens every position's roster into individual employees, each
 * carrying its own position (for salary) alongside its own identity/
 * active-window fields — this is the "by employee" dropdown's source list. */
export function flattenEmployees(rows) {
  return rows.flatMap((row) => (row.employees || []).map((employee) => ({ employee, row })))
}

/** Which pay periods (by index) this employee is active/paid for, given
 * the pay periods built by buildPayPeriods — biweekly periods inherit
 * their shared month's single active/inactive flag. */
export function activePeriodsForEmployee(employee, payPeriods, selectedYear, calendarMode) {
  const monthlyActive = employeeMonthlyActive(employee, selectedYear, calendarMode)
  return payPeriods.map((period) => monthlyActive[period.monthIndex])
}

/** Sums a group of `{ employee, breakdown }` entries (all sharing the same
 * country, so their item lists line up by position) into one array of
 * per-period totals — the Summary view's "all employees" rows and the
 * By-Employee view's single-employee table both reduce to this. Every
 * entry's annual figures are divided by checksPerYear and added into
 * whichever periods that employee is actually active for. */
export function aggregatePeriodsForGroup(groupEntries, payPeriods, selectedYear, calendarMode, checksPerYear) {
  const employerTaxLabels = groupEntries[0]?.breakdown.employerTaxItems.map((item) => item.label) ?? []
  const employerBenefitsLabels = groupEntries[0]?.breakdown.employerBenefitsItems.map((item) => item.label) ?? []
  const employeeLabels = groupEntries[0]?.breakdown.employeeItems.map((item) => item.label) ?? []
  const periods = payPeriods.map(() => ({
    gross: 0,
    employerTaxItems: employerTaxLabels.map((label) => ({ label, amount: 0 })),
    employerTaxTotal: 0,
    employerBenefitsItems: employerBenefitsLabels.map((label) => ({ label, amount: 0 })),
    employerBenefitsTotal: 0,
    employerTotal: 0,
    employeeItems: employeeLabels.map((label) => ({ label, amount: 0 })),
    employeeTotalWithheld: 0,
    net: 0,
    activeCount: 0,
  }))

  groupEntries.forEach(({ employee, breakdown }) => {
    const active = activePeriodsForEmployee(employee, payPeriods, selectedYear, calendarMode)
    const perCheckGross = breakdown.grossAnnual / checksPerYear
    const perCheckEmployerTaxItems = breakdown.employerTaxItems.map((item) => item.annualAmount / checksPerYear)
    const perCheckEmployerTaxTotal = breakdown.employerTaxTotalAnnual / checksPerYear
    const perCheckEmployerBenefitsItems = breakdown.employerBenefitsItems.map((item) => item.annualAmount / checksPerYear)
    const perCheckEmployerBenefitsTotal = breakdown.employerBenefitsTotalAnnual / checksPerYear
    const perCheckEmployeeItems = breakdown.employeeItems.map((item) => item.annualAmount / checksPerYear)
    const perCheckEmployeeTotalWithheld = breakdown.employeeTotalWithheldAnnual / checksPerYear
    const perCheckNet = breakdown.netAnnual / checksPerYear

    active.forEach((isActive, periodIndex) => {
      if (!isActive) return
      const bucket = periods[periodIndex]
      bucket.gross += perCheckGross
      bucket.employerTaxTotal += perCheckEmployerTaxTotal
      bucket.employerBenefitsTotal += perCheckEmployerBenefitsTotal
      bucket.employerTotal += perCheckEmployerTaxTotal + perCheckEmployerBenefitsTotal
      bucket.employeeTotalWithheld += perCheckEmployeeTotalWithheld
      bucket.net += perCheckNet
      bucket.activeCount += 1
      perCheckEmployerTaxItems.forEach((amount, index) => {
        bucket.employerTaxItems[index].amount += amount
      })
      perCheckEmployerBenefitsItems.forEach((amount, index) => {
        bucket.employerBenefitsItems[index].amount += amount
      })
      perCheckEmployeeItems.forEach((amount, index) => {
        bucket.employeeItems[index].amount += amount
      })
    })
  })

  return periods
}
