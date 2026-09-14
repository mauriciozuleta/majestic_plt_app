import { DAYS_PER_MONTH, isoDateToSimDate, simDateToIsoDate } from '../../../../shared/SimulationCalendar/simulationCalendarMath'
import { shiftIsoDate } from './calendarViewMath'

export const MAX_OCCURRENCES = 366

export const FREQUENCIES = [
  { key: 'daily', label: 'Daily', unit: 'day' },
  { key: 'weekly', label: 'Weekly', unit: 'week' },
  { key: 'monthly', label: 'Monthly', unit: 'month' },
  // Twice a month on 2 fixed calendar days (mirrors Settings > Payroll
  // Schedule's own biweekly concept) — distinct from "Weekly, every 2",
  // which is a rolling every-14-days-from-start pattern instead.
  { key: 'biweekly', label: 'Biweekly', unit: null },
  { key: 'custom', label: 'Custom', unit: null },
]

export const UNITS = [
  { key: 'day', label: 'Day(s)' },
  { key: 'week', label: 'Week(s)' },
  { key: 'month', label: 'Month(s)' },
]

export const DAYS_1_TO_30 = Array.from({ length: 30 }, (_, index) => index + 1)

/** Adds whole months to an ISO date while keeping the same day-of-month
 * (clamped to the shorter month, e.g. Jan 31 + 1 month -> Feb 28). In
 * simulation mode every month is a fixed 30 days, so this is exact day math. */
function addMonthsPreservingDay(calendarMode, isoDate, months) {
  if (calendarMode === 'simulation') {
    return shiftIsoDate(isoDate, months * DAYS_PER_MONTH)
  }
  const date = new Date(`${isoDate}T00:00:00`)
  const day = date.getDate()
  date.setDate(1)
  date.setMonth(date.getMonth() + months)
  const daysInTargetMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
  date.setDate(Math.min(day, daysInTargetMonth))
  const year = String(date.getFullYear()).padStart(4, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const dayStr = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${dayStr}`
}

function yearMonthOf(calendarMode, isoDate) {
  if (calendarMode === 'simulation') {
    const { year, month } = isoDateToSimDate(isoDate)
    return { year, month }
  }
  const [year, month] = isoDate.split('-').map(Number)
  return { year, month }
}

/** One calendar-day-of-month, clamped to however many days that month
 * actually has (e.g. day 30 in a real February clamps to 28/29; simulation
 * months are always exactly DAYS_PER_MONTH long, so day is only clamped to
 * that range there). */
function isoDateFromYearMonthDay(calendarMode, year, month, day) {
  if (calendarMode === 'simulation') {
    return simDateToIsoDate({ year, month, day: Math.min(day, DAYS_PER_MONTH) })
  }
  const daysInMonth = new Date(year, month, 0).getDate()
  const clampedDay = Math.min(day, daysInMonth)
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(clampedDay).padStart(2, '0')}`
}

function nextYearMonth(year, month) {
  return month >= 12 ? { year: year + 1, month: 1 } : { year, month: month + 1 }
}

/** Expands a "pay on day(s) N of every month" schedule into concrete ISO
 * dates from startIsoDate through untilIsoDate (inclusive) — `days` is
 * `[day]` for a once-a-month schedule or `[day1, day2]` for a twice-a-month
 * one. Used both for the "Biweekly" recurrence frequency itself and for
 * resolving each occurrence's own payment day under the Monthly/Biweekly
 * payment-schedule modes. */
export function buildMonthlyDayDates(calendarMode, startIsoDate, untilIsoDate, days) {
  const sortedDays = [...days].sort((a, b) => a - b)
  let { year, month } = yearMonthOf(calendarMode, startIsoDate)
  const dates = []

  while (dates.length < MAX_OCCURRENCES) {
    for (const day of sortedDays) {
      const candidate = isoDateFromYearMonthDay(calendarMode, year, month, day)
      if (candidate < startIsoDate) continue
      if (untilIsoDate && candidate > untilIsoDate) return dates
      dates.push(candidate)
      if (dates.length >= MAX_OCCURRENCES) return dates
    }
    ;({ year, month } = nextYearMonth(year, month))
    if (untilIsoDate && isoDateFromYearMonthDay(calendarMode, year, month, 1) > untilIsoDate) break
  }
  return dates
}

/** The payment day to use for one occurrence dated entryIsoDate, under a
 * Monthly (1 day) or Biweekly (2 days) payment schedule — the earliest
 * configured day on or after the entry's own date within that same month,
 * or the first configured day of the next month if none are left. */
export function resolveNextPayday(calendarMode, entryIsoDate, days) {
  const sortedDays = [...days].sort((a, b) => a - b)
  const { year, month } = yearMonthOf(calendarMode, entryIsoDate)

  for (const day of sortedDays) {
    const candidate = isoDateFromYearMonthDay(calendarMode, year, month, day)
    if (candidate >= entryIsoDate) return candidate
  }
  const { year: nextYear, month: nextMonth } = nextYearMonth(year, month)
  return isoDateFromYearMonthDay(calendarMode, nextYear, nextMonth, sortedDays[0])
}

function resolveUnit(frequency, customUnit) {
  if (frequency === 'custom') return customUnit || 'day'
  return FREQUENCIES.find((item) => item.key === frequency)?.unit ?? 'day'
}

/** Expands a recurrence rule into concrete ISO dates, starting at
 * startIsoDate and stopping at untilIsoDate (inclusive) or MAX_OCCURRENCES,
 * whichever comes first. For frequency 'custom', customUnit ('day' | 'week'
 * | 'month') picks the step unit; for the named presets the unit is implied.
 * 'biweekly' ignores interval/customUnit entirely — it's always twice a
 * month on the two configured biweeklyDays. */
export function buildRecurrenceDates(calendarMode, startIsoDate, { frequency, customUnit, interval, untilIsoDate, biweeklyDays }) {
  if (frequency === 'biweekly') {
    const days = Array.isArray(biweeklyDays) && biweeklyDays.length === 2 ? biweeklyDays : [1, 15]
    return buildMonthlyDayDates(calendarMode, startIsoDate, untilIsoDate, days)
  }

  const step = Math.max(1, Number(interval) || 1)
  const unit = resolveUnit(frequency, customUnit)
  const dates = [startIsoDate]
  let current = startIsoDate

  while (dates.length < MAX_OCCURRENCES) {
    if (unit === 'day') {
      current = shiftIsoDate(current, step)
    } else if (unit === 'week') {
      current = shiftIsoDate(current, step * 7)
    } else if (unit === 'month') {
      current = addMonthsPreservingDay(calendarMode, current, step)
    } else {
      break
    }
    if (!untilIsoDate || current > untilIsoDate) break
    dates.push(current)
  }
  return dates
}
