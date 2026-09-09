import { DAYS_PER_MONTH } from '../../../../shared/SimulationCalendar/simulationCalendarMath'
import { shiftIsoDate } from './calendarViewMath'

export const MAX_OCCURRENCES = 366

export const FREQUENCIES = [
  { key: 'daily', label: 'Daily', unit: 'day' },
  { key: 'weekly', label: 'Weekly', unit: 'week' },
  { key: 'monthly', label: 'Monthly', unit: 'month' },
  { key: 'custom', label: 'Custom', unit: null },
]

export const UNITS = [
  { key: 'day', label: 'Day(s)' },
  { key: 'week', label: 'Week(s)' },
  { key: 'month', label: 'Month(s)' },
]

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

function resolveUnit(frequency, customUnit) {
  if (frequency === 'custom') return customUnit || 'day'
  return FREQUENCIES.find((item) => item.key === frequency)?.unit ?? 'day'
}

/** Expands a recurrence rule into concrete ISO dates, starting at
 * startIsoDate and stopping at untilIsoDate (inclusive) or MAX_OCCURRENCES,
 * whichever comes first. For frequency 'custom', customUnit ('day' | 'week'
 * | 'month') picks the step unit; for the named presets the unit is implied. */
export function buildRecurrenceDates(calendarMode, startIsoDate, { frequency, customUnit, interval, untilIsoDate }) {
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
