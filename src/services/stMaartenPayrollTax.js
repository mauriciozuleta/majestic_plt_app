// Sint Maarten (Dutch side — "St Marteen" in this app's location data)
// payroll tax structure: SZV social-insurance premiums (AOV, AWW, BVZ, AVBZ,
// ZV, OV) plus progressive wage tax with the 25% local surtax already
// folded into the bracket rates below.
//
// SOURCES (best available — flagged where uncertain, since unlike the US
// module there is no worked example from the user to validate against):
// - SZV premium percentages: Global Expansion "Global Hiring Guide: Sint
//   Maarten" (rev. April 2023). The BVZ rate (9.3%) was independently
//   reconfirmed as the CURRENT 2025 rate by a Celery Payroll 2025 tax
//   update (reporting it dropped from 11.7% to 9.3% for 2025), so AOV/AWW/
//   BVZ/AVBZ/ZV are treated as still current. OV is an SZV-assigned
//   per-employer accident-risk-class rate (0.5%-5%), not a single published
//   number — exposed here as a configurable rate, not a constant.
// - 2025 wage-tax exemption threshold and the AOV/AWW wage ceiling: SZV's
//   own "2025 AOV/AWW Amounts" publication (szv.sx), cross-referenced with
//   Bloomberg Tax's report of the government's 2025 tax-table posting.
// - Wage-tax BRACKET BOUNDARIES are the 2023 table (Global Expansion) — the
//   2025 boundaries are reported as "somewhat wider" (i.e. lower tax at the
//   same salary) but the exact new numbers weren't available from any
//   source reachable here. Using the narrower 2023 boundaries means this
//   OVERSTATES wage tax slightly at the margins — the safe direction for a
//   cost model, but still worth confirming against a real 2025/2026 payslip.
//
// Salaries in this app are plain USD numbers (same convention already used
// for Colombia — no currency conversion happens elsewhere in Payroll), so
// this module converts to ANG internally (via a live or fallback rate) to
// apply the ANG-denominated law, then converts results back to USD.

export const SZV_EMPLOYER_RATES = {
  aov: 0.06,
  aww: 0.005,
  bvz: 0.093,
  avbz: 0.005,
  zv: 0.019,
}

export const SZV_EMPLOYEE_RATES = {
  aov: 0.09,
  aww: 0.005,
  bvz: 0.043,
  avbz: 0.015,
}

export const OV_RATE_MIN = 0.005
export const OV_RATE_MAX = 0.05
// No single published "average" — SZV assigns this per employer based on
// accident risk class. Defaulting to the low end of the range as a
// placeholder for a typical office/admin role.
export const OV_RATE_DEFAULT = 0.015

export const EMPLOYER_BASE_RATE = Object.values(SZV_EMPLOYER_RATES).reduce((sum, rate) => sum + rate, 0)
export const EMPLOYEE_BASE_RATE = Object.values(SZV_EMPLOYEE_RATES).reduce((sum, rate) => sum + rate, 0)

export const AOV_AWW_WAGE_CEILING_ANG = 131966.57 // 2025, annual
export const WAGE_TAX_EXEMPTION_ANG = 27106.56 // 2025, annual

// Effective rates already include the 25% local surtax (e.g. 10% base + 25%
// surtax = 12.5%). Boundaries are the 2023 table — see source note above.
export const WAGE_TAX_BRACKETS_ANG = [
  { upTo: 31837, rate: 0.125 },
  { upTo: 47756, rate: 0.2 },
  { upTo: 66328, rate: 0.2525 },
  { upTo: 99490, rate: 0.3375 },
  { upTo: 140612, rate: 0.4 },
  { upTo: Infinity, rate: 0.475 },
]

// Historical fixed peg (ANG has been pegged to USD since 1971) — used only
// if a live rate can't be fetched.
export const ANG_PER_USD_FALLBACK = 1.79

export function computeProgressiveTax(taxableAmount, brackets) {
  let remaining = Math.max(0, taxableAmount)
  let tax = 0
  let previousUpTo = 0

  for (const bracket of brackets) {
    if (remaining <= 0) break
    const bracketSize = bracket.upTo - previousUpTo
    const amountInBracket = Math.min(remaining, bracketSize)
    tax += amountInBracket * bracket.rate
    remaining -= amountInBracket
    previousUpTo = bracket.upTo
  }

  return tax
}

export function computeEmployerPayrollTax(annualSalaryUsd, angPerUsd, ovRate = OV_RATE_DEFAULT) {
  const salaryAng = annualSalaryUsd * angPerUsd
  const aovAwwWageAng = Math.min(salaryAng, AOV_AWW_WAGE_CEILING_ANG)

  const aov = aovAwwWageAng * SZV_EMPLOYER_RATES.aov
  const aww = aovAwwWageAng * SZV_EMPLOYER_RATES.aww
  const bvz = salaryAng * SZV_EMPLOYER_RATES.bvz
  const avbz = salaryAng * SZV_EMPLOYER_RATES.avbz
  const zv = salaryAng * SZV_EMPLOYER_RATES.zv
  const ov = salaryAng * ovRate
  const totalAng = aov + aww + bvz + avbz + zv + ov

  return {
    aov: aov / angPerUsd,
    aww: aww / angPerUsd,
    bvz: bvz / angPerUsd,
    avbz: avbz / angPerUsd,
    zv: zv / angPerUsd,
    ov: ov / angPerUsd,
    total: totalAng / angPerUsd,
  }
}

export function computeEmployeeWithholding(annualSalaryUsd, angPerUsd) {
  const salaryAng = annualSalaryUsd * angPerUsd
  const aovAwwWageAng = Math.min(salaryAng, AOV_AWW_WAGE_CEILING_ANG)

  const aov = aovAwwWageAng * SZV_EMPLOYEE_RATES.aov
  const aww = aovAwwWageAng * SZV_EMPLOYEE_RATES.aww
  const bvz = salaryAng * SZV_EMPLOYEE_RATES.bvz
  const avbz = salaryAng * SZV_EMPLOYEE_RATES.avbz
  const socialPremiumsAng = aov + aww + bvz + avbz

  const taxableAng = Math.max(0, salaryAng - WAGE_TAX_EXEMPTION_ANG)
  const wageTaxAng = computeProgressiveTax(taxableAng, WAGE_TAX_BRACKETS_ANG)

  const totalWithheldAng = socialPremiumsAng + wageTaxAng
  const netAnnualAng = salaryAng - totalWithheldAng

  return {
    aov: aov / angPerUsd,
    aww: aww / angPerUsd,
    bvz: bvz / angPerUsd,
    avbz: avbz / angPerUsd,
    socialPremiums: socialPremiumsAng / angPerUsd,
    wageTax: wageTaxAng / angPerUsd,
    totalWithheld: totalWithheldAng / angPerUsd,
    netAnnual: netAnnualAng / angPerUsd,
  }
}

const ST_MAARTEN_LOCATION_ALIASES = new Set([
  'st marteen',
  'st. marteen',
  'st maarten',
  'st. maarten',
  'sint maarten',
])

export function isStMaartenLocation(location) {
  return ST_MAARTEN_LOCATION_ALIASES.has(String(location || '').trim().toLowerCase())
}
