import { isoDateToSimDate } from '../../../../shared/SimulationCalendar/simulationCalendarMath'

/**
 * Which of the 12 months within its own year a stored date falls in (1-12).
 * The date's own YEAR component is never used here — start_projection_year /
 * end_projection_year are the authoritative year, this only answers "which
 * month inside that year." Works for both calendar modes: simulation dates
 * decode through the fictitious 30-day-month calendar; real dates just read
 * their real calendar month.
 */
export function monthWithinYear(dateStr, calendarMode) {
  if (!dateStr) return 1
  if (calendarMode === 'simulation') {
    try {
      return isoDateToSimDate(dateStr).month
    } catch {
      return 1
    }
  }
  const parsed = new Date(`${dateStr}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? 1 : parsed.getUTCMonth() + 1
}

/**
 * 12 booleans (months 1-12 of `selectedYear`) telling whether this employee
 * was active that month, derived from their start/end projection years plus
 * which month within those years their start/end date falls in.
 */
export function employeeMonthlyActive(employee, selectedYear, calendarMode) {
  const startYear = employee.start_projection_year ?? 0
  const endYear = employee.end_projection_year

  let startMonth
  if (startYear > selectedYear) startMonth = 13 // hasn't started yet this year
  else if (startYear < selectedYear) startMonth = 1 // already on board coming into this year
  else startMonth = monthWithinYear(employee.start_date, calendarMode)

  let endMonth
  if (endYear == null) endMonth = 12
  else if (endYear < selectedYear) endMonth = 0 // already left before this year
  else if (endYear > selectedYear) endMonth = 12
  else endMonth = monthWithinYear(employee.end_date, calendarMode)

  const months = []
  for (let month = 1; month <= 12; month += 1) months.push(month >= startMonth && month <= endMonth)
  return months
}

/** Sums employeeMonthlyActive across every employee on a position into a 12-length headcount array. */
export function positionMonthlyHeadcount(employees, selectedYear, calendarMode) {
  const totals = new Array(12).fill(0)
  ;(employees || []).forEach((employee) => {
    employeeMonthlyActive(employee, selectedYear, calendarMode).forEach((active, index) => {
      if (active) totals[index] += 1
    })
  })
  return totals
}
