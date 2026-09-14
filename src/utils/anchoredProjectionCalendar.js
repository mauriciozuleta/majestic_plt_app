// Real-mode counterpart to simulationCalendarMath.js's simDateToIsoDate /
// isoDateToSimDate — same 30-day-month / 360-day-year day-count convention,
// just anchored at an arbitrary real date (Settings' persisted
// real_start_date) instead of the fictitious epoch, since real calendar
// mode has no "day zero" of its own. Used wherever a projection year/month
// needs a real calendar date (or vice versa) outside simulation mode —
// Payroll Schedule's automatic entry generation, and Expenses reading real
// Commercial Operations dates back into a projection year/month.
const MS_PER_DAY = 24 * 60 * 60 * 1000
const DAYS_PER_MONTH = 30
const DAYS_PER_YEAR = DAYS_PER_MONTH * 12

function isoToUtcDate(isoDate) {
  const [year, month, day] = String(isoDate).split('-').map(Number)
  // Date.UTC(year, ...) silently treats a year 0-99 as 1900+year — building
  // with a safe year and overwriting via setUTCFullYear sidesteps that (only
  // matters for a fictitious-epoch-adjacent anchor, but kept for safety).
  const date = new Date(Date.UTC(2000, month - 1, day))
  date.setUTCFullYear(year)
  return date
}

function utcDateToIsoDate(date) {
  const year = String(date.getUTCFullYear()).padStart(4, '0')
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function anchoredYearMonthDayToIsoDate(anchorIsoDate, year, month, day) {
  const elapsedDays = (year - 1) * DAYS_PER_YEAR + (month - 1) * DAYS_PER_MONTH + (day - 1)
  const anchor = isoToUtcDate(anchorIsoDate)
  anchor.setUTCDate(anchor.getUTCDate() + elapsedDays)
  return utcDateToIsoDate(anchor)
}

export function isoDateToAnchoredYearMonth(anchorIsoDate, isoDate) {
  const elapsedDays = Math.round((isoToUtcDate(isoDate) - isoToUtcDate(anchorIsoDate)) / MS_PER_DAY)
  const year = Math.floor(elapsedDays / DAYS_PER_YEAR) + 1
  const dayOfYear = ((elapsedDays % DAYS_PER_YEAR) + DAYS_PER_YEAR) % DAYS_PER_YEAR
  const month = Math.floor(dayOfYear / DAYS_PER_MONTH) + 1
  return { year, month }
}
