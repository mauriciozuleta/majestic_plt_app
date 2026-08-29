import { formatSimulationDate } from '../components/shared/SimulationCalendar/formatSimulationDate'
import { isoDateToSimDate, simDateToIsoDate } from '../components/shared/SimulationCalendar/simulationCalendarMath'

export function toDisplayDate(isoDate, calendarMode) {
  if (calendarMode !== 'simulation') return isoDate
  return formatSimulationDate(isoDate)
}

export function fromSimulationInput(year, month, day) {
  return simDateToIsoDate({ year, month, day })
}

export function toSimulationParts(isoDate) {
  return isoDateToSimDate(isoDate)
}
