// US employee benefits — each modeled as a flat % of salary (employer
// share + employee share), consistent with how the rest of the US payroll
// tax structure is expressed (see usPayrollTax.js). Real benefit costs are
// negotiated per plan/company and aren't standardized percentages the way
// FICA/FUTA/SUTA are — the rates here are illustrative defaults, not a
// published standard, and are meant to be adjusted per company.
//
// Each benefit also declares which taxable-wage bases its EMPLOYEE share
// reduces, since pre-tax ("Section 125" or traditional retirement) benefit
// contributions lower what tax is actually owed on, not just what's paid
// out of pocket:
//  - reducesFederalWages / reducesStateWages: true for anything pre-tax
//    (401(k) deferrals reduce these but not payroll-tax wages).
//  - reducesPayrollTaxWages: true only for genuine Section 125 cafeteria-
//    plan benefits (health/dental/vision/HSA/FSA) — real IRS treatment
//    also exempts these from Social Security, Medicare, FUTA, and SUTA
//    wages, unlike a traditional 401(k) deferral.
// Employer-paid-only benefits (life, disability, workers' comp) reduce
// nothing — they're a pure add-on cost, never a payroll deduction.
import {
  computeEmployeeWithholding as computeBaseEmployeeWithholding,
  computeEmployerPayrollTax as computeBaseEmployerPayrollTax,
} from './usPayrollTax'

export const US_BENEFITS = [
  {
    key: '401k',
    label: '401(k) Retirement Match',
    description:
      'Employer-sponsored retirement plan. Employee elective deferrals are pre-tax for federal and state income tax, but still subject to Social Security and Medicare.',
    employerPct: 0.03,
    employeePct: 0.05,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: false,
  },
  {
    key: 'health',
    label: 'Health Insurance (Medical)',
    description:
      "Section 125 cafeteria-plan medical premiums. The employee's share is pre-tax for federal, state, Social Security, and Medicare.",
    employerPct: 0.06,
    employeePct: 0.02,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: true,
  },
  {
    key: 'dental',
    label: 'Dental Insurance',
    description: 'Section 125 dental premiums — same pre-tax treatment as health insurance.',
    employerPct: 0.005,
    employeePct: 0.003,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: true,
  },
  {
    key: 'vision',
    label: 'Vision Insurance',
    description: 'Section 125 vision premiums — same pre-tax treatment as health insurance.',
    employerPct: 0.002,
    employeePct: 0.001,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: true,
  },
  {
    key: 'hsa',
    label: 'Health Savings Account (HSA)',
    description:
      'Pre-tax savings for medical expenses, paired with a high-deductible health plan. Both employer and employee contributions are pre-tax for federal, state, Social Security, and Medicare.',
    employerPct: 0.01,
    employeePct: 0.02,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: true,
  },
  {
    key: 'fsa',
    label: 'Flexible Spending Account (FSA)',
    description:
      'Pre-tax account for medical or dependent-care expenses. Employee contributions reduce federal, state, Social Security, and Medicare wages.',
    employerPct: 0,
    employeePct: 0.01,
    reducesFederalWages: true,
    reducesStateWages: true,
    reducesPayrollTaxWages: true,
  },
  {
    key: 'lifeInsurance',
    label: 'Life Insurance (Basic)',
    description:
      'Employer-paid group term life insurance. A pure employer cost — not a payroll deduction (coverage over $50,000 is technically imputed income to the employee, which this model does not add back in).',
    employerPct: 0.003,
    employeePct: 0,
    reducesFederalWages: false,
    reducesStateWages: false,
    reducesPayrollTaxWages: false,
  },
  {
    key: 'disability',
    label: 'Disability Insurance (Short/Long-Term)',
    description: 'Employer-paid income-replacement insurance. A pure employer cost — not a payroll deduction.',
    employerPct: 0.005,
    employeePct: 0,
    reducesFederalWages: false,
    reducesStateWages: false,
    reducesPayrollTaxWages: false,
  },
  {
    key: 'workersComp',
    label: "Workers' Compensation",
    description: 'State-mandated insurance covering workplace injuries. A pure employer cost — never deducted from employee pay.',
    employerPct: 0.0075,
    employeePct: 0,
    reducesFederalWages: false,
    reducesStateWages: false,
    reducesPayrollTaxWages: false,
  },
]

/** Per-benefit and total employer/employee dollar amounts for the
 * currently-enabled benefits, plus how much each taxable-wage base should
 * be reduced by (the sum of enabled benefits' EMPLOYEE share that are
 * flagged as reducing that base). */
export function computeBenefitsCost(annualSalary, enabledKeys) {
  const salary = Number(annualSalary) || 0
  const enabled = new Set(enabledKeys || [])
  let employerTotal = 0
  let employeeTotal = 0
  let federalReduction = 0
  let stateReduction = 0
  let payrollTaxReduction = 0
  const breakdown = []

  US_BENEFITS.forEach((benefit) => {
    if (!enabled.has(benefit.key)) return
    const employerAmount = salary * benefit.employerPct
    const employeeAmount = salary * benefit.employeePct
    employerTotal += employerAmount
    employeeTotal += employeeAmount
    if (benefit.reducesFederalWages) federalReduction += employeeAmount
    if (benefit.reducesStateWages) stateReduction += employeeAmount
    if (benefit.reducesPayrollTaxWages) payrollTaxReduction += employeeAmount
    breakdown.push({ ...benefit, employerAmount, employeeAmount })
  })

  return { employerTotal, employeeTotal, federalReduction, stateReduction, payrollTaxReduction, breakdown }
}

/** Employer payroll tax + benefits cost combined — what the position
 * actually costs the company on top of salary, with any enabled Section
 * 125 benefits correctly shrinking the payroll-tax wage base first. */
export function computeFullEmployerCost(annualSalary, enabledBenefitKeys = []) {
  const salary = Number(annualSalary) || 0
  const benefits = computeBenefitsCost(salary, enabledBenefitKeys)
  const payrollTaxWage = Math.max(0, salary - benefits.payrollTaxReduction)
  const payrollTax = computeBaseEmployerPayrollTax(salary, { payrollTaxWage })
  return {
    payrollTax,
    benefitsEmployerCost: benefits.employerTotal,
    benefitsBreakdown: benefits.breakdown,
    total: payrollTax.total + benefits.employerTotal,
  }
}

/** Employee withholding + benefit deductions combined — take-home pay
 * after taxes AND the employee's own elected benefit contributions, with
 * each tax computed against its correctly-reduced wage base. */
export function computeFullEmployeeWithholding(annualSalary, stateName, paychecksPerYear = 24, enabledBenefitKeys = []) {
  const salary = Number(annualSalary) || 0
  const benefits = computeBenefitsCost(salary, enabledBenefitKeys)
  const payrollTaxWage = Math.max(0, salary - benefits.payrollTaxReduction)
  const federalTaxableWage = Math.max(0, salary - benefits.federalReduction)
  const stateTaxableWage = Math.max(0, salary - benefits.stateReduction)
  const withholding = computeBaseEmployeeWithholding(salary, stateName, paychecksPerYear, {
    payrollTaxWage,
    federalTaxableWage,
    stateTaxableWage,
    employeeBenefitContributions: benefits.employeeTotal,
  })
  return { ...withholding, benefitsEmployeeCost: benefits.employeeTotal, benefitsBreakdown: benefits.breakdown }
}
