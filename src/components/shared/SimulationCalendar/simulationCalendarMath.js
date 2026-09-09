export const FICTITIOUS_EPOCH = '0001-01-01'
export const DAYS_PER_MONTH = 30
export const MONTHS_PER_YEAR = 12
export const DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR

const MS_PER_DAY = 24 * 60 * 60 * 1000

function isoToUtcDate(isoDate) {
  const [year, month, day] = String(isoDate).split('-').map(Number)
  if ([year, month, day].some((value) => Number.isNaN(value))) {
    throw new Error(`Invalid ISO date: ${isoDate}`)
  }

  // Date.UTC(year, ...) silently treats any year 0-99 as 1900+year (a
  // legacy two-digit-year quirk) — the fictitious epoch's year 1 would
  // otherwise become 1901. Building with a safe year and overwriting it via
  // setUTCFullYear sidesteps that: setUTCFullYear has no such special case.
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

function daysBetween(a, b) {
  return Math.round((isoToUtcDate(b) - isoToUtcDate(a)) / MS_PER_DAY)
}

export function isoDateToSimDate(isoDate) {
  const elapsed = daysBetween(FICTITIOUS_EPOCH, isoDate)
  // Year 1 is the first operational year, starting exactly at the fictitious
  // epoch — there is no "Year 0" (all pre-operational activity now lives in
  // the Start-up Investment module, not on this calendar).
  const year = Math.floor(elapsed / DAYS_PER_YEAR) + 1
  const dayOfYear = ((elapsed % DAYS_PER_YEAR) + DAYS_PER_YEAR) % DAYS_PER_YEAR
  const month = Math.floor(dayOfYear / DAYS_PER_MONTH) + 1
  const day = (dayOfYear % DAYS_PER_MONTH) + 1
  return { year, month, day }
}

export function simDateToIsoDate({ year, month, day }) {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    throw new Error('Simulation date values must be integers')
  }
  if (month < 1 || month > MONTHS_PER_YEAR) {
    throw new Error('Simulation month must be between 1 and 12')
  }
  if (day < 1 || day > DAYS_PER_MONTH) {
    throw new Error('Simulation day must be between 1 and 30')
  }

  const elapsedDays = (year - 1) * DAYS_PER_YEAR + (month - 1) * DAYS_PER_MONTH + (day - 1)
  const epoch = isoToUtcDate(FICTITIOUS_EPOCH)
  epoch.setUTCDate(epoch.getUTCDate() + elapsedDays)
  return utcDateToIsoDate(epoch)
}

export function dateToIsoDate(date) {
  return utcDateToIsoDate(
    new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate())),
  )
}

export function parseIsoDate(isoDate) {
  return isoToUtcDate(isoDate)
}

export const MONTH_OPTIONS = Array.from({ length: MONTHS_PER_YEAR }, (_, index) => index + 1)
export const DAY_OPTIONS = Array.from({ length: DAYS_PER_MONTH }, (_, index) => index + 1)
