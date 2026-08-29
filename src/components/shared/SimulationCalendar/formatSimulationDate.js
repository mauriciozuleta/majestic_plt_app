import { isoDateToSimDate } from './simulationCalendarMath'

export function formatSimulationDate(isoDate) {
  const { year, month, day } = isoDateToSimDate(isoDate)
  return `Year ${year}, Month ${month}, Day ${day}`
}

export function formatSimulationDateCompact(isoDate) {
  const { year, month, day } = isoDateToSimDate(isoDate)
  return `Y${year} M${month} D${day}`
}
