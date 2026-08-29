import {
  formatSimulationDateFromDate,
  parseIsoToDate,
  SIMULATION_STORAGE_EPOCH,
} from '../../../../../services/calendarDates'

const ZOOM_DAY_WIDTH = { Day: 40, Week: 14, Month: 4 }

export function getDateRange(tasks, calendarMode = 'real') {
  if (!tasks.length) {
    if (calendarMode === 'simulation') {
      const simulationStart = parseIsoToDate(SIMULATION_STORAGE_EPOCH)
      return { start: simulationStart, end: addDays(simulationStart, 30) }
    }

    const today = new Date()
    return { start: today, end: addDays(today, 30) }
  }

  const starts = tasks.map((task) => parseIsoToDate(task.start)).filter(Boolean)
  const ends = tasks.map((task) => parseIsoToDate(task.end)).filter(Boolean)
  const start = new Date(Math.min(...starts))
  const end = new Date(Math.max(...ends))

  return { start: addDays(start, -3), end: addDays(end, 10) }
}

export function addDays(date, days) {
  const nextDate = new Date(date)
  nextDate.setDate(nextDate.getDate() + days)
  nextDate.setHours(0, 0, 0, 0)
  return nextDate
}

export function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / (1000 * 60 * 60 * 24))
}

export function getDayWidth(zoom) {
  return ZOOM_DAY_WIDTH[zoom] ?? ZOOM_DAY_WIDTH.Week
}

export function getBarGeometry(task, rangeStart, dayWidth) {
  const left = daysBetween(rangeStart, parseIsoToDate(task.start)) * dayWidth
  const width = Math.max(daysBetween(parseIsoToDate(task.start), parseIsoToDate(task.end)) * dayWidth, dayWidth)
  return { left, width }
}

export function getHeaderSegments(rangeStart, rangeEnd, zoom, dayWidth, calendarMode = 'real') {
  const segments = []
  let cursor = new Date(rangeStart)
  const stepDays = zoom === 'Month' ? 30 : 7

  while (cursor < rangeEnd) {
    const segmentEnd = addDays(cursor, stepDays)
    const label =
      calendarMode === 'simulation'
        ? formatSimulationDateFromDate(cursor)
        : zoom === 'Month'
          ? cursor.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
          : cursor.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

    segments.push({
      label,
      width: stepDays * dayWidth,
    })
    cursor = segmentEnd
  }

  return segments
}
