// Colombia payroll tax structure — mandatory social security (pensión,
// salud, ARL), parafiscales (Caja de Compensación, ICBF, SENA),
// prestaciones sociales (cesantías, intereses sobre cesantías, prima de
// servicios), the FSP (Fondo de Solidaridad Pensional) surcharge for
// higher earners, and the monthly wage-withholding table for salaried
// employees (retención en la fuente, Art. 383 E.T. as amended by Ley 2277
// de 2022).
//
// Reference figures (SMMLV, UVT) are user-editable in the Settings panel
// and persisted on PortfolioSettings, since they're indexed annually by the
// Colombian government — SMMLV_COP_DEFAULT/UVT_COP_DEFAULT below are only
// the fallback used until the user sets their own values.
//
// Simplifications:
// - The IBC (contribution base income) cap of 25 SMMLV/month is applied
//   uniformly to every employer contribution, not just pensión/salud where
//   it's most commonly cited.
// - The "exoneración de aportes" (Ley 1607 de 2012 / Ley 1819 de 2016) —
//   employers don't pay salud, SENA, or ICBF for employees earning under
//   10 SMMLV/month — is modeled, assuming a standard income-tax-paying
//   corporate employer (the common case; some employer types don't qualify).
// - Auxilio de transporte (a flat transport subsidy for low earners) is not
//   modeled — it's a fixed amount, not a %, and doesn't apply to most
//   management-tier roles.
//
// Salaries in this app are plain USD numbers (same convention as the rest
// of Payroll) — this module converts to COP internally (live or fallback
// rate) to apply the law, then converts results back to USD.

export const SMMLV_COP_DEFAULT = 1750905 // 2026
export const UVT_COP_DEFAULT = 52374 // 2026

export const IBC_CEILING_SMMLV = 25
export const EXONERACION_THRESHOLD_SMMLV = 10

export const EMPLOYER_RATES = {
  pension: 0.12,
  salud: 0.085, // waived below 10 SMMLV — see EXONERACION_THRESHOLD_SMMLV
  caja: 0.04,
  icbf: 0.03, // waived below 10 SMMLV
  sena: 0.02, // waived below 10 SMMLV
  cesantias: 0.0833,
  interesesCesantias: 0.01,
  prima: 0.0833,
}

export const ARL_RISK_CLASSES = [
  { key: 'I', label: 'Class I — minimal risk (offices)', rate: 0.00522 },
  { key: 'II', label: 'Class II — low risk', rate: 0.01044 },
  { key: 'III', label: 'Class III — medium risk', rate: 0.02436 },
  { key: 'IV', label: 'Class IV — high risk', rate: 0.0435 },
  { key: 'V', label: 'Class V — maximum risk', rate: 0.0696 },
]
export const ARL_DEFAULT_CLASS_KEY = 'I'

export const EMPLOYEE_RATES = {
  pension: 0.04,
  salud: 0.04,
}

// FSP (Fondo de Solidaridad Pensional) — additional employee pension %,
// on top of the base 4%, based on multiples of SMMLV.
export const FSP_BRACKETS = [
  { minSmmlv: 4, maxSmmlv: 16, rate: 0.01 },
  { minSmmlv: 16, maxSmmlv: 17, rate: 0.012 },
  { minSmmlv: 17, maxSmmlv: 18, rate: 0.014 },
  { minSmmlv: 18, maxSmmlv: 19, rate: 0.016 },
  { minSmmlv: 19, maxSmmlv: 20, rate: 0.018 },
  { minSmmlv: 20, maxSmmlv: Infinity, rate: 0.02 },
]

// Monthly wage withholding table (retención en la fuente para
// asalariados), in UVT — Art. 383 E.T. as amended by Ley 2277 de 2022.
// tax = base + (taxable_UVT - from) * rate
export const WITHHOLDING_BRACKETS_UVT = [
  { from: 0, to: 95, rate: 0, base: 0 },
  { from: 95, to: 150, rate: 0.19, base: 0 },
  { from: 150, to: 360, rate: 0.28, base: 10 },
  { from: 360, to: 640, rate: 0.33, base: 69 },
  { from: 640, to: 945, rate: 0.35, base: 162 },
  { from: 945, to: 2300, rate: 0.37, base: 268 },
  { from: 2300, to: Infinity, rate: 0.39, base: 770 },
]

// The standard 25% "renta exenta" labor-income exemption (Art. 206 #10
// E.T.), capped at 790 UVT per YEAR.
export const RENTA_EXENTA_RATE = 0.25
export const RENTA_EXENTA_ANNUAL_CAP_UVT = 790

export const COP_PER_USD_FALLBACK = 4000 // rough, floats freely (not pegged) — prefer the live rate

export function getFspRate(monthlySalaryCop, smmlvCop) {
  const multiples = monthlySalaryCop / smmlvCop
  if (multiples < 4) return 0
  const bracket = FSP_BRACKETS.find((b) => multiples >= b.minSmmlv && multiples < b.maxSmmlv)
  return bracket ? bracket.rate : FSP_BRACKETS[FSP_BRACKETS.length - 1].rate
}

export function computeMonthlyWithholdingUvt(monthlyTaxableUvt) {
  if (monthlyTaxableUvt <= 95) return 0
  const bracket = WITHHOLDING_BRACKETS_UVT.find((b) => monthlyTaxableUvt > b.from && monthlyTaxableUvt <= b.to)
  if (!bracket) return 0
  return bracket.base + (monthlyTaxableUvt - bracket.from) * bracket.rate
}

export function computeEmployerPayrollTax(annualSalaryUsd, copPerUsd, arlRate, smmlvCop = SMMLV_COP_DEFAULT) {
  const annualSalaryCop = annualSalaryUsd * copPerUsd
  const monthlySalaryCop = annualSalaryCop / 12
  const ibcCop = Math.min(monthlySalaryCop, IBC_CEILING_SMMLV * smmlvCop)
  const exempt = monthlySalaryCop < EXONERACION_THRESHOLD_SMMLV * smmlvCop

  const pension = ibcCop * EMPLOYER_RATES.pension
  const salud = exempt ? 0 : ibcCop * EMPLOYER_RATES.salud
  const arl = ibcCop * arlRate
  const caja = ibcCop * EMPLOYER_RATES.caja
  const icbf = exempt ? 0 : ibcCop * EMPLOYER_RATES.icbf
  const sena = exempt ? 0 : ibcCop * EMPLOYER_RATES.sena
  const cesantias = monthlySalaryCop * EMPLOYER_RATES.cesantias
  const interesesCesantias = monthlySalaryCop * EMPLOYER_RATES.interesesCesantias
  const prima = monthlySalaryCop * EMPLOYER_RATES.prima

  const monthlyTotalCop = pension + salud + arl + caja + icbf + sena + cesantias + interesesCesantias + prima
  const annualTotalCop = monthlyTotalCop * 12

  return {
    pension: (pension * 12) / copPerUsd,
    salud: (salud * 12) / copPerUsd,
    arl: (arl * 12) / copPerUsd,
    caja: (caja * 12) / copPerUsd,
    icbf: (icbf * 12) / copPerUsd,
    sena: (sena * 12) / copPerUsd,
    cesantias: (cesantias * 12) / copPerUsd,
    interesesCesantias: (interesesCesantias * 12) / copPerUsd,
    prima: (prima * 12) / copPerUsd,
    exonerado: exempt,
    total: annualTotalCop / copPerUsd,
  }
}

export function computeEmployeeWithholding(
  annualSalaryUsd,
  copPerUsd,
  smmlvCop = SMMLV_COP_DEFAULT,
  uvtCop = UVT_COP_DEFAULT,
) {
  const annualSalaryCop = annualSalaryUsd * copPerUsd
  const monthlySalaryCop = annualSalaryCop / 12
  const ibcCop = Math.min(monthlySalaryCop, IBC_CEILING_SMMLV * smmlvCop)

  const fspRate = getFspRate(monthlySalaryCop, smmlvCop)
  const pension = ibcCop * EMPLOYEE_RATES.pension
  const fsp = ibcCop * fspRate
  const salud = ibcCop * EMPLOYEE_RATES.salud
  const socialSecurityCop = pension + fsp + salud

  const baseAfterSocialSecurity = monthlySalaryCop - socialSecurityCop
  const rentaExentaCapCop = (RENTA_EXENTA_ANNUAL_CAP_UVT / 12) * uvtCop
  const rentaExenta = Math.min(baseAfterSocialSecurity * RENTA_EXENTA_RATE, rentaExentaCapCop)
  const taxableBaseCop = Math.max(0, baseAfterSocialSecurity - rentaExenta)
  const taxableBaseUvt = taxableBaseCop / uvtCop

  const monthlyWithholdingUvt = computeMonthlyWithholdingUvt(taxableBaseUvt)
  const monthlyWithholdingCop = monthlyWithholdingUvt * uvtCop

  const monthlyTotalWithheldCop = socialSecurityCop + monthlyWithholdingCop
  const monthlyNetCop = monthlySalaryCop - monthlyTotalWithheldCop

  return {
    fspRate,
    pension: (pension * 12) / copPerUsd,
    fsp: (fsp * 12) / copPerUsd,
    salud: (salud * 12) / copPerUsd,
    socialSecurity: (socialSecurityCop * 12) / copPerUsd,
    withholding: (monthlyWithholdingCop * 12) / copPerUsd,
    totalWithheld: (monthlyTotalWithheldCop * 12) / copPerUsd,
    netAnnual: (monthlyNetCop * 12) / copPerUsd,
  }
}

const COLOMBIA_LOCATION_ALIASES = new Set(['col', 'colombia'])

export function isColombiaLocation(location) {
  return COLOMBIA_LOCATION_ALIASES.has(String(location || '').trim().toLowerCase())
}
