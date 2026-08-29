import { useEffect, useMemo, useRef, useState } from 'react'
import { IconCalendarEvent } from '@tabler/icons-react'
import { formatCalendarDate } from '../../../../../services/calendarDates'

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH_LABELS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function parseIsoDate(value) {
  if (!value) return null
  const parts = value.split('-').map(Number)
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) return null

  const [year, month, day] = parts
  const parsed = new Date(0)
  parsed.setFullYear(year, month - 1, day)
  parsed.setHours(0, 0, 0, 0)
  if (Number.isNaN(parsed.getTime())) return null

  return parsed
}

function formatIsoDate(date) {
  const year = String(date.getFullYear()).padStart(4, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function createDateWithYear(year, month, day) {
  const date = new Date(0)
  date.setFullYear(year, month, day)
  date.setHours(0, 0, 0, 0)
  return date
}

function sameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function buildCalendarDays(monthDate) {
  const year = monthDate.getFullYear()
  const month = monthDate.getMonth()
  const firstDay = createDateWithYear(year, month, 1).getDay()
  const daysInMonth = createDateWithYear(year, month + 1, 0).getDate()
  const daysInPrevMonth = createDateWithYear(year, month, 0).getDate()

  const cells = []

  for (let i = firstDay - 1; i >= 0; i -= 1) {
    const day = daysInPrevMonth - i
    cells.push({
      date: createDateWithYear(year, month - 1, day),
      inCurrentMonth: false,
    })
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({
      date: createDateWithYear(year, month, day),
      inCurrentMonth: true,
    })
  }

  while (cells.length % 7 !== 0) {
    const nextDay = cells.length - (firstDay + daysInMonth) + 1
    cells.push({
      date: createDateWithYear(year, month + 1, nextDay),
      inCurrentMonth: false,
    })
  }

  return cells
}

function RoadmapDateInput({ value, onChange, id, ariaLabel, calendarMode = 'real' }) {
  const containerRef = useRef(null)
  const selectedDate = parseIsoDate(value)
  const [isOpen, setIsOpen] = useState(false)
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const baseline = selectedDate ?? new Date()
    return createDateWithYear(baseline.getFullYear(), baseline.getMonth(), 1)
  })

  useEffect(() => {
    const baseline = selectedDate ?? new Date()
    setVisibleMonth(createDateWithYear(baseline.getFullYear(), baseline.getMonth(), 1))
  }, [value])

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick)
    }
  }, [])

  const monthLabel = `${MONTH_LABELS[visibleMonth.getMonth()]} ${visibleMonth.getFullYear()}`
  const calendarDays = useMemo(() => buildCalendarDays(visibleMonth), [visibleMonth])

  return (
    <div className="roadmap-date-picker" ref={containerRef}>
      <button
        id={id}
        type="button"
        className="roadmap-date-input"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={ariaLabel}
      >
        <span>{value ? formatCalendarDate(value, calendarMode) : 'YYYY-MM-DD'}</span>
        <IconCalendarEvent size={15} stroke={1.8} />
      </button>

      {isOpen && (
        <div className="roadmap-date-picker__calendar" role="dialog" aria-label="Date picker">
          <div className="roadmap-date-picker__header">
            <button
              type="button"
              className="roadmap-date-picker__nav"
              onClick={() =>
                setVisibleMonth(
                  (prev) => createDateWithYear(prev.getFullYear(), prev.getMonth() - 1, 1),
                )
              }
              aria-label="Previous month"
            >
              {'<'}
            </button>
            <strong>{monthLabel}</strong>
            <button
              type="button"
              className="roadmap-date-picker__nav"
              onClick={() =>
                setVisibleMonth(
                  (prev) => createDateWithYear(prev.getFullYear(), prev.getMonth() + 1, 1),
                )
              }
              aria-label="Next month"
            >
              {'>'}
            </button>
          </div>

          <div className="roadmap-date-picker__weekdays">
            {WEEKDAY_LABELS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>

          <div className="roadmap-date-picker__grid">
            {calendarDays.map((cell) => {
              const isSelected = selectedDate ? sameDay(cell.date, selectedDate) : false
              return (
                <button
                  key={`${cell.date.toISOString()}-${cell.inCurrentMonth ? 'current' : 'adjacent'}`}
                  type="button"
                  className={`roadmap-date-picker__day ${
                    cell.inCurrentMonth ? '' : 'is-muted'
                  } ${isSelected ? 'is-selected' : ''}`}
                  onClick={() => {
                    onChange(formatIsoDate(cell.date))
                    setIsOpen(false)
                  }}
                >
                  {cell.date.getDate()}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default RoadmapDateInput
