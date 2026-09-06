import { DAYS_PER_MONTH, isoDateToSimDate, simDateToIsoDate } from '../../../../shared/SimulationCalendar/simulationCalendarMath'

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const REAL_MONTH_LABELS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export { WEEKDAY_LABELS }

function toIsoDate(date) {
  const year = String(date.getFullYear()).padStart(4, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Shifts a stored ISO date by a number of real days. Works uniformly for
 * both calendar modes — a simulation date is just a fixed reinterpretation
 * of elapsed days from a fictitious epoch, so shifting the underlying ISO
 * string and re-decoding it lands on the correct simulation day too. */
export function shiftIsoDate(isoDate, deltaDays) {
  const date = new Date(`${isoDate}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + deltaDays)
  return date.toISOString().slice(0, 10)
}

export function shiftMonth(calendarMode, referenceIsoDate, delta) {
  if (calendarMode === 'simulation') {
    return shiftIsoDate(referenceIsoDate, delta * DAYS_PER_MONTH)
  }
  const date = new Date(`${referenceIsoDate}T00:00:00`)
  date.setMonth(date.getMonth() + delta, 1)
  return toIsoDate(date)
}

function realMonthCells(referenceIsoDate) {
  const anchor = new Date(`${referenceIsoDate}T00:00:00`)
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const firstWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const daysInPrevMonth = new Date(year, month, 0).getDate()

  const cells = []
  for (let i = firstWeekday - 1; i >= 0; i -= 1) {
    cells.push({ isoDate: toIsoDate(new Date(year, month - 1, daysInPrevMonth - i)), inCurrentPeriod: false })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ isoDate: toIsoDate(new Date(year, month, day)), inCurrentPeriod: true })
  }
  while (cells.length % 7 !== 0) {
    const nextDay = cells.length - (firstWeekday + daysInMonth) + 1
    cells.push({ isoDate: toIsoDate(new Date(year, month + 1, nextDay)), inCurrentPeriod: false })
  }
  return cells
}

function simMonthCells(referenceIsoDate) {
  const { year, month } = isoDateToSimDate(referenceIsoDate)
  const firstDayIso = simDateToIsoDate({ year, month, day: 1 })
  return Array.from({ length: DAYS_PER_MONTH }, (_, index) => ({
    isoDate: shiftIsoDate(firstDayIso, index),
    inCurrentPeriod: true,
  }))
}

export function getMonthCells(calendarMode, referenceIsoDate) {
  return calendarMode === 'simulation' ? simMonthCells(referenceIsoDate) : realMonthCells(referenceIsoDate)
}

export function getMonthLabel(calendarMode, referenceIsoDate) {
  if (calendarMode === 'simulation') {
    const { year, month } = isoDateToSimDate(referenceIsoDate)
    return `Year ${year}, Month ${month}`
  }
  const date = new Date(`${referenceIsoDate}T00:00:00`)
  return `${REAL_MONTH_LABELS[date.getMonth()]} ${date.getFullYear()}`
}

export function getDayNumber(calendarMode, isoDate) {
  if (calendarMode === 'simulation') {
    return isoDateToSimDate(isoDate).day
  }
  return new Date(`${isoDate}T00:00:00`).getDate()
}

export function getYear(calendarMode, isoDate) {
  if (calendarMode === 'simulation') {
    return isoDateToSimDate(isoDate).year
  }
  return new Date(`${isoDate}T00:00:00`).getFullYear()
}

/** Jumps the reference date to a different year, keeping the same month/day
 * (or the same simulation month/day) so a year pick doesn't also reset
 * whatever month or day the user was looking at. */
export function setYear(calendarMode, isoDate, year) {
  if (calendarMode === 'simulation') {
    const { month, day } = isoDateToSimDate(isoDate)
    return simDateToIsoDate({ year, month, day })
  }
  const date = new Date(`${isoDate}T00:00:00`)
  date.setFullYear(year)
  return toIsoDate(date)
}

export function getDayLabel(calendarMode, isoDate) {
  if (calendarMode === 'simulation') {
    const { year, month, day } = isoDateToSimDate(isoDate)
    return `Year ${year}, Month ${month}, Day ${day}`
  }
  const date = new Date(`${isoDate}T00:00:00`)
  return date.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
}
