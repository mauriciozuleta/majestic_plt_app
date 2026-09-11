// US payroll tax structure — Employer and Employee sides, kept as small,
// pure, independently-testable functions (no framework/UI dependencies)
// so the same math can be reused wherever it's needed: Expenses (employer
// cost) and Settings > Tax Structure (employee withholding + paycheck
// preview). This is a deliberately simplified model — flat percentages on
// full gross annual salary, no wage-base caps (Social Security, FUTA,
// SUTA all normally cap out in reality), no standard deduction, single
// filer only for federal brackets. That's a real simplification, not an
// oversight: it's what reproduces the worked example this module was
// verified against (see usPayrollTax.verify.mjs in project history) —
// $280,000 salary -> employer cost +$30,520/yr, employee federal tax
// $67,547.25/yr, 24 paychecks of $7,259.70 each (assuming a 6% flat state
// rate, since real state tax codes have their own brackets/rules this
// model doesn't attempt to reproduce exactly — see US_STATE_TAX_RATES).

// A position's "location" is free text from wherever it was entered/
// imported (e.g. "USA" from the payroll import template), not the
// commercial structure's own country name ("United States") — matching it
// needs a small alias set rather than an exact-name comparison. Used to
// scope US-specific payroll math (this module, benefits, inflation) to
// only the positions it actually describes.
const USA_LOCATION_ALIASES = new Set(['usa', 'us', 'united states', 'united states of america'])

export function isUsaLocation(location) {
  return USA_LOCATION_ALIASES.has(String(location || '').trim().toLowerCase())
}

export const EMPLOYER_TAX_RATES = {
  socialSecurity: 0.062,
  medicare: 0.0145,
  additionalMedicareThreshold: 200000,
  additionalMedicareRate: 0.009,
  futa: 0.006,
  suta: 0.0175,
}

// The base rate (excluding the conditional Additional Medicare surcharge)
// — this is the flat "10%" the structure was specified with.
export const EMPLOYER_BASE_RATE =
  EMPLOYER_TAX_RATES.socialSecurity + EMPLOYER_TAX_RATES.medicare + EMPLOYER_TAX_RATES.futa + EMPLOYER_TAX_RATES.suta

/** Employer-side payroll tax cost for one position's annual salary — what
 * it costs the company on TOP of the salary itself. The Additional
 * Medicare surcharge (when salary exceeds the threshold) is applied to
 * the FULL salary, not just the excess over the threshold — that's the
 * specified structure, and it's what reproduces the worked example
 * ($280,000 -> +$30,520/yr = 10% + 0.9%, both on the full $280,000).
 *
 * `options.payrollTaxWage`, if given, is the wage base these taxes are
 * actually computed against (and what the Additional Medicare threshold
 * check uses) — pre-tax benefit deductions (Section 125 health/dental/
 * vision/HSA/FSA) reduce this below the raw salary; see usBenefits.js.
 * Defaults to the salary itself, so existing callers that don't pass
 * options are unaffected. */
export function computeEmployerPayrollTax(annualSalary, options = {}) {
  const salary = Number(annualSalary) || 0
  const payrollTaxWage = options.payrollTaxWage ?? salary
  const socialSecurity = payrollTaxWage * EMPLOYER_TAX_RATES.socialSecurity
  const medicare = payrollTaxWage * EMPLOYER_TAX_RATES.medicare
  const additionalMedicare =
    payrollTaxWage > EMPLOYER_TAX_RATES.additionalMedicareThreshold ? payrollTaxWage * EMPLOYER_TAX_RATES.additionalMedicareRate : 0
  const futa = payrollTaxWage * EMPLOYER_TAX_RATES.futa
  const suta = payrollTaxWage * EMPLOYER_TAX_RATES.suta
  const total = socialSecurity + medicare + additionalMedicare + futa + suta
  return {
    socialSecurity,
    medicare,
    additionalMedicare,
    futa,
    suta,
    total,
    rate: salary > 0 ? total / salary : 0,
  }
}

// 2025 IRS single-filer federal income tax brackets (Rev. Proc. 2024-40).
// Applied directly to gross annual salary — no standard deduction
// subtracted first, single filing status only. That combination is what
// reproduces the worked example's federal tax figure exactly; a real
// paycheck's withholding also depends on filing status, W-4 elections,
// and deductions this model doesn't attempt to capture.
export const FEDERAL_TAX_BRACKETS_2025_SINGLE = [
  { upTo: 11925, rate: 0.1 },
  { upTo: 48475, rate: 0.12 },
  { upTo: 103350, rate: 0.22 },
  { upTo: 197300, rate: 0.24 },
  { upTo: 250525, rate: 0.32 },
  { upTo: 626350, rate: 0.35 },
  { upTo: Infinity, rate: 0.37 },
]

/** Progressive federal income tax on a given amount of income, using the
 * supplied bracket table (each bracket taxed only on the portion of
 * income that falls within it). */
export function computeProgressiveTax(income, brackets) {
  const amount = Number(income) || 0
  let tax = 0
  let lowerBound = 0
  for (const bracket of brackets) {
    if (amount <= lowerBound) break
    const taxableInThisBracket = Math.min(amount, bracket.upTo) - lowerBound
    tax += taxableInThisBracket * bracket.rate
    lowerBound = bracket.upTo
  }
  return tax
}

export function computeFederalTax(annualSalary, brackets = FEDERAL_TAX_BRACKETS_2025_SINGLE) {
  return computeProgressiveTax(annualSalary, brackets)
}

// Simplified reference state income tax rates — each state's top/flat
// marginal rate, used as a single flat percentage rather than modeling
// every state's own bracket structure (most states are progressive; a
// few are genuinely flat). This is intentionally an approximation for
// payroll cost estimation, not a substitute for each state's real
// withholding tables. 0% for the states with no wage income tax.
export const US_STATE_TAX_RATES = {
  Alabama: 0.05,
  Alaska: 0,
  Arizona: 0.025,
  Arkansas: 0.039,
  California: 0.133,
  Colorado: 0.044,
  Connecticut: 0.0699,
  Delaware: 0.066,
  Florida: 0,
  Georgia: 0.0519,
  Hawaii: 0.11,
  Idaho: 0.058,
  Illinois: 0.0495,
  Indiana: 0.0305,
  Iowa: 0.038,
  Kansas: 0.057,
  Kentucky: 0.04,
  Louisiana: 0.03,
  Maine: 0.0715,
  Maryland: 0.0575,
  Massachusetts: 0.05,
  Michigan: 0.0425,
  Minnesota: 0.0985,
  Mississippi: 0.044,
  Missouri: 0.047,
  Montana: 0.059,
  Nebraska: 0.052,
  Nevada: 0,
  'New Hampshire': 0,
  'New Jersey': 0.1075,
  'New Mexico': 0.059,
  'New York': 0.109,
  'North Carolina': 0.0425,
  'North Dakota': 0.025,
  Ohio: 0.035,
  Oklahoma: 0.0475,
  Oregon: 0.099,
  Pennsylvania: 0.0307,
  'Rhode Island': 0.0599,
  'South Carolina': 0.062,
  'South Dakota': 0,
  Tennessee: 0,
  Texas: 0,
  Utah: 0.0455,
  Vermont: 0.0875,
  Virginia: 0.0575,
  Washington: 0,
  'West Virginia': 0.0482,
  Wisconsin: 0.0765,
  Wyoming: 0,
  'District of Columbia': 0.1075,
}

export const US_STATES = Object.keys(US_STATE_TAX_RATES).sort()

export function getStateTaxRate(stateName) {
  return US_STATE_TAX_RATES[stateName] ?? 0
}

export const EMPLOYEE_TAX_RATES = {
  socialSecurity: 0.062,
  medicare: 0.0145,
}

/** Employee-side withholding for a given annual salary and (optionally)
 * a selected state. `paychecksPerYear` defaults to 24 (semi-monthly).
 *
 * `options.payrollTaxWage` / `federalTaxableWage` / `stateTaxableWage`,
 * each independently, let a pre-tax benefit deduction (see usBenefits.js)
 * reduce the wage base ONE of these taxes is actually computed against —
 * real Section 125 plans reduce all three; a traditional 401(k) reduces
 * only the federal/state ones. All default to the salary itself, so
 * existing callers that don't pass options are unaffected.
 * `options.employeeBenefitContributions`, if given, is also subtracted
 * from take-home pay (the employee's own elected contribution amount —
 * money that leaves the paycheck without being a tax). */
export function computeEmployeeWithholding(annualSalary, stateName = null, paychecksPerYear = 24, options = {}) {
  const salary = Number(annualSalary) || 0
  const payrollTaxWage = options.payrollTaxWage ?? salary
  const federalTaxableWage = options.federalTaxableWage ?? salary
  const stateTaxableWage = options.stateTaxableWage ?? salary
  const employeeBenefitContributions = options.employeeBenefitContributions ?? 0
  const socialSecurity = payrollTaxWage * EMPLOYEE_TAX_RATES.socialSecurity
  const medicare = payrollTaxWage * EMPLOYEE_TAX_RATES.medicare
  const federalTax = computeFederalTax(federalTaxableWage)
  const stateRate = stateName ? getStateTaxRate(stateName) : 0
  const stateTax = stateTaxableWage * stateRate
  const totalWithheld = socialSecurity + medicare + federalTax + stateTax
  const netAnnual = salary - totalWithheld - employeeBenefitContributions
  const perCheck = paychecksPerYear > 0 ? netAnnual / paychecksPerYear : netAnnual
  return {
    socialSecurity,
    medicare,
    federalTax,
    stateTax,
    stateRate,
    totalWithheld,
    employeeBenefitContributions,
    netAnnual,
    perCheck,
    paychecksPerYear,
  }
}
