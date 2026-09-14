// Turns live Payroll data into the Commercial Operations entries Settings >
// Payroll Schedule's "Automatic schedule" promises — one entry per pay
// period per category (Payroll / Payroll Tax Expense / Employee Benefits),
// across every configured projection year, tagged so they can be safely
// re-diffed on every payroll change without ever double-posting.
import { simDateToIsoDate } from '../../../../shared/SimulationCalendar/simulationCalendarMath'
import { anchoredYearMonthDayToIsoDate } from '../../../../../utils/anchoredProjectionCalendar'
import { shiftIsoDate } from '../../OperationsTab/CommercialOperationsView/calendarViewMath'
import { fetchSettings } from '../../../../../services/settings'
import { fetchPayrollScheduleSettings } from '../../../../../services/payrollScheduleSettings'
import { fetchPayroll } from '../../../../../services/payroll'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import { COP_PER_USD_FALLBACK } from '../../../../../services/colombiaPayrollTax'
import { ANG_PER_USD_FALLBACK } from '../../../../../services/stMaartenPayrollTax'
import {
  fetchCommercialOperationEntries,
  createCommercialOperationEntry,
  updateCommercialOperationEntry,
  deleteCommercialOperationEntry,
} from '../../../../../services/commercialOperations'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { useAppStore } from '../../../../../store/useAppStore'
import {
  aggregatePeriodsForGroup,
  buildPayPeriods,
  computeAnnualBreakdown,
  flattenEmployees,
  getChecksPerYear,
} from './payrollDisbursement'

const MIN_POSTABLE_AMOUNT = 0.01
export const PAYROLL_SCHEDULE_SOURCE = 'payroll_schedule'

function computeEntryDate({ calendarMode, realStartDate, projectionYear, monthIndex, day }) {
  if (calendarMode === 'simulation') {
    return simDateToIsoDate({ year: projectionYear, month: monthIndex + 1, day })
  }
  return anchoredYearMonthDayToIsoDate(realStartDate, projectionYear, monthIndex + 1, day)
}

const CATEGORY_DEFS = [
  { key: 'payroll', description: 'Payroll', treatment: 'payroll', bucketKey: 'gross' },
  { key: 'taxes', description: 'Payroll Tax Expense', treatment: 'tax', bucketKey: 'employerTaxTotal' },
  { key: 'benefits', description: 'Employee Benefits', treatment: 'benefits', bucketKey: 'employerBenefitsTotal' },
]

/** Builds the full "should exist" set of Payroll Schedule entries across
 * every configured projection year, from live payroll data — one entry per
 * pay period per non-zero category that has a bank account configured for
 * it. Pure function: given the same inputs, always returns the same set, so
 * the caller can safely diff it against whatever already exists and only
 * touch what actually changed. */
export function buildDesiredPayrollScheduleEntries({
  rowsByYear,
  projectionYears,
  payrollScheduleType,
  scheduleMonthlyDay,
  scheduleBiweeklyDay1,
  scheduleBiweeklyDay2,
  calendarMode,
  realStartDate,
  enabledBenefitKeys,
  companyCountryCode,
  colombiaRates,
  angPerUsd,
  usState,
  bankAccountIdsByCategory,
}) {
  const checksPerYear = getChecksPerYear(payrollScheduleType)
  const payPeriods = buildPayPeriods(payrollScheduleType, calendarMode)
  const periodsPerMonth = payPeriods.length / 12
  const desired = []

  for (let projectionYear = 1; projectionYear <= projectionYears; projectionYear += 1) {
    const rows = rowsByYear[projectionYear] || []
    if (rows.length === 0) continue

    const context = { enabledBenefitKeys, checksPerYear, colombiaRates, angPerUsd, companyCountryCode, usState }
    const breakdownByNodeId = new Map(rows.map((row) => [row.node_id, computeAnnualBreakdown(row, context)]))
    const employeeEntries = flattenEmployees(rows).map(({ employee, row }) => ({
      employee,
      row,
      breakdown: breakdownByNodeId.get(row.node_id),
    }))
    const periods = aggregatePeriodsForGroup(employeeEntries, payPeriods, projectionYear, calendarMode, checksPerYear)

    payPeriods.forEach((payPeriod, periodIndex) => {
      const bucket = periods[periodIndex]
      const half = periodsPerMonth > 1 ? (payPeriod.index % periodsPerMonth) + 1 : null
      const day = (payrollScheduleType === 'biweekly' ? (half === 2 ? scheduleBiweeklyDay2 : scheduleBiweeklyDay1) : scheduleMonthlyDay) || 1
      const entryDate = computeEntryDate({ calendarMode, realStartDate, projectionYear, monthIndex: payPeriod.monthIndex, day })

      CATEGORY_DEFS.forEach(({ key, description, treatment, bucketKey }) => {
        const amount = bucket[bucketKey]
        const bankAccountId = bankAccountIdsByCategory[key]
        if (!bankAccountId || !(amount > MIN_POSTABLE_AMOUNT)) return
        desired.push({
          schedule_key: `${projectionYear}:${payPeriod.index}:${key}`,
          category: 'expenses',
          description,
          accounting_treatment: treatment,
          amount,
          entry_date: entryDate,
          // A day after entry_date (not equal to it — gl_engine treats an
          // equal settlement_date as "no separate settlement leg" at all)
          // so the actual cash-leaving-the-bank posting exists and shows up
          // in the Cash Flow Statement, instead of the amount sitting in
          // Payroll/Tax/Benefits Payable forever unrealized.
          settlement_date: shiftIsoDate(entryDate, 1),
          bank_account_id: bankAccountId,
          source: PAYROLL_SCHEDULE_SOURCE,
        })
      })
    })
  }

  return desired
}

/** Diffs `desiredEntries` (empty when Automatic Schedule is off) against
 * whatever this company already has tagged source: 'payroll_schedule', and
 * creates/updates/deletes only what actually changed — safe to call
 * repeatedly, since unchanged entries are left untouched (no needless GL
 * re-posting). Turning Automatic Schedule off is just calling this with an
 * empty desired set, which the same diff cleanly deletes everything for. */
export async function syncPayrollScheduleEntries(companyId, desiredEntries) {
  const existingEntries = (await fetchCommercialOperationEntries(companyId)).filter(
    (entry) => entry.source === PAYROLL_SCHEDULE_SOURCE,
  )
  const existingByKey = new Map(existingEntries.map((entry) => [entry.schedule_key, entry]))
  const desiredByKey = new Map(desiredEntries.map((entry) => [entry.schedule_key, entry]))

  let created = 0
  let updated = 0
  let deleted = 0

  for (const [key, desired] of desiredByKey) {
    const existing = existingByKey.get(key)
    if (!existing) {
      // eslint-disable-next-line no-await-in-loop
      await createCommercialOperationEntry(companyId, desired)
      created += 1
      continue
    }
    const changed =
      Math.abs(existing.amount - desired.amount) > 0.005 ||
      existing.entry_date !== desired.entry_date ||
      existing.settlement_date !== desired.settlement_date ||
      existing.bank_account_id !== desired.bank_account_id
    if (changed) {
      // eslint-disable-next-line no-await-in-loop
      await updateCommercialOperationEntry(companyId, existing.id, { ...existing, ...desired })
      updated += 1
    }
  }

  for (const [key, existing] of existingByKey) {
    if (!desiredByKey.has(key)) {
      // eslint-disable-next-line no-await-in-loop
      await deleteCommercialOperationEntry(companyId, existing.id)
      deleted += 1
    }
  }

  if (created > 0 || updated > 0 || deleted > 0) {
    broadcastCompanyDataChange(companyId, 'payroll-schedule:sync')
  }

  return { created, updated, deleted }
}

/** One-stop orchestration: gathers everything buildDesiredPayrollScheduleEntries
 * needs (settings, bank-account choices, every projection year's payroll
 * rows, FX rates) and runs the sync — used both by the reactive hook
 * (usePayrollScheduleSync) and by the Payroll Schedule panel's own "save"
 * action, so the gather-then-sync logic exists in exactly one place. */
export async function runPayrollScheduleSync(companyId) {
  const [settings, scheduleSettings] = await Promise.all([fetchSettings(), fetchPayrollScheduleSettings(companyId)])

  if (!scheduleSettings.automatic_schedule) {
    return syncPayrollScheduleEntries(companyId, [])
  }

  const companyCountryCode = useAppStore.getState().companies.find((company) => company.id === companyId)?.countryCode
  const projectionYears = Math.max(5, Math.min(10, settings.projection_years || 5))
  const years = Array.from({ length: projectionYears }, (_, index) => index + 1)

  const [rowsList, angRate] = await Promise.all([
    Promise.all(years.map((year) => fetchPayroll(companyId, year))),
    fetchExchangeRate('ANG', 'USD').catch(() => null),
  ])
  const rowsByYear = Object.fromEntries(years.map((year, index) => [year, rowsList[index]]))

  const desiredEntries = buildDesiredPayrollScheduleEntries({
    rowsByYear,
    projectionYears,
    payrollScheduleType: settings.payroll_schedule_type === 'biweekly' ? 'biweekly' : 'monthly',
    scheduleMonthlyDay: settings.payroll_schedule_monthly_day,
    scheduleBiweeklyDay1: settings.payroll_schedule_biweekly_day1,
    scheduleBiweeklyDay2: settings.payroll_schedule_biweekly_day2,
    calendarMode: settings.calendar_mode === 'simulation' ? 'simulation' : 'real',
    realStartDate: settings.real_start_date,
    enabledBenefitKeys: Array.isArray(settings.enabled_benefits) ? settings.enabled_benefits : [],
    companyCountryCode,
    colombiaRates: {
      copPerUsd: settings.colombia_projected_cop_per_usd || COP_PER_USD_FALLBACK,
      smmlvCop: settings.colombia_smmlv_cop,
      uvtCop: settings.colombia_uvt_cop,
    },
    angPerUsd: angRate?.rate > 0 ? 1 / angRate.rate : ANG_PER_USD_FALLBACK,
    usState: settings.us_payroll_state || '',
    bankAccountIdsByCategory: {
      payroll: scheduleSettings.payroll_bank_account_id,
      taxes: scheduleSettings.taxes_bank_account_id,
      benefits: scheduleSettings.benefits_bank_account_id,
    },
  })

  return syncPayrollScheduleEntries(companyId, desiredEntries)
}
