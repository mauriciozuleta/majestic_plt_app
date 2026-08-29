import { formatSimulationDate, formatSimulationDateCompact } from '../components/shared/SimulationCalendar/formatSimulationDate'
import {
  FICTITIOUS_EPOCH,
  dateToIsoDate,
  parseIsoDate,
  simDateToIsoDate,
} from '../components/shared/SimulationCalendar/simulationCalendarMath'

export const SIMULATION_STORAGE_EPOCH = FICTITIOUS_EPOCH

export function getDefaultCalendarDate(calendarMode) {
  return calendarMode === 'simulation'
    ? simDateToIsoDate({ year: 0, month: 1, day: 1 })
    : new Date().toISOString().slice(0, 10)
}

export { formatSimulationDate }

export function formatCalendarDate(isoDate, calendarMode) {
  if (calendarMode === 'simulation') {
    return formatSimulationDate(isoDate)
  }
  return isoDate
}

export function formatCalendarDateCompact(isoDate, calendarMode) {
  if (calendarMode === 'simulation') {
    return formatSimulationDateCompact(isoDate)
  }
  return isoDate
}

export function formatSimulationDateFromDate(date) {
  return formatSimulationDateCompact(dateToIsoDate(date))
}

export function parseIsoToDate(isoDate) {
  try {
    return parseIsoDate(isoDate)
  } catch {
    return null
  }
}
