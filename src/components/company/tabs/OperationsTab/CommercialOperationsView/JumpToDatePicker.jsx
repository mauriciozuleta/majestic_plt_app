import { useEffect, useRef, useState } from 'react'
import { IconCalendarEvent } from '@tabler/icons-react'
import { getDayNumber, getMonthCells, getMonthLabel, shiftMonth } from './calendarViewMath'

/** A small popup month-grid for jumping straight to a date, in front of the
 * "prev/next one step at a time" arrows. Works for both calendar modes since
 * calendarViewMath's helpers already are mode-aware, so there's no need for
 * a separate simulation-mode variant. */
function JumpToDatePicker({ calendarMode, value, onChange }) {
  const containerRef = useRef(null)
  const [isOpen, setIsOpen] = useState(false)
  const [visibleAnchor, setVisibleAnchor] = useState(value)

  useEffect(() => {
    if (isOpen) setVisibleAnchor(value)
  }, [isOpen, value])

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setIsOpen(false)
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [])

  const cells = getMonthCells(calendarMode, visibleAnchor)

  return (
    <div className="commercial-ops-date-picker" ref={containerRef}>
      <button
        type="button"
        className="commercial-ops-date-picker__trigger"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label="Pick a date"
      >
        <IconCalendarEvent size={15} stroke={1.8} />
        Pick date
      </button>

      {isOpen && (
        <div className="commercial-ops-date-picker__popup" role="dialog" aria-label="Date picker">
          <div className="commercial-ops-date-picker__header">
            <button
              type="button"
              onClick={() => setVisibleAnchor((prev) => shiftMonth(calendarMode, prev, -1))}
              aria-label="Previous month"
            >
              {'<'}
            </button>
            <strong>{getMonthLabel(calendarMode, visibleAnchor)}</strong>
            <button
              type="button"
              onClick={() => setVisibleAnchor((prev) => shiftMonth(calendarMode, prev, 1))}
              aria-label="Next month"
            >
              {'>'}
            </button>
          </div>

          <div className="commercial-ops-date-picker__grid">
            {cells.map((cell) => (
              <button
                key={cell.isoDate}
                type="button"
                className={`commercial-ops-date-picker__day ${cell.inCurrentPeriod ? '' : 'is-muted'} ${
                  cell.isoDate === value ? 'is-selected' : ''
                }`}
                onClick={() => {
                  onChange(cell.isoDate)
                  setIsOpen(false)
                }}
              >
                {getDayNumber(calendarMode, cell.isoDate)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default JumpToDatePicker
