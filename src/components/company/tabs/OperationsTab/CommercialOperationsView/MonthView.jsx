import { WEEKDAY_LABELS, getDayNumber, getMonthCells } from './calendarViewMath'
import { CATEGORIES } from './categories'

function MonthView({ calendarMode, referenceDate, entriesByDate, onSelectDay }) {
  const cells = getMonthCells(calendarMode, referenceDate)

  return (
    <div className="commercial-ops-month">
      {calendarMode !== 'simulation' && (
        <div className="commercial-ops-month__weekdays">
          {WEEKDAY_LABELS.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      )}
      <div className="commercial-ops-month__grid">
        {cells.map((cell) => {
          const dayEntries = entriesByDate.get(cell.isoDate) || []
          const totalsByCategory = CATEGORIES.map((category) => ({
            ...category,
            total: dayEntries.filter((entry) => entry.category === category.key).reduce((sum, entry) => sum + entry.amount, 0),
          })).filter((category) => category.total > 0)

          return (
            <button
              type="button"
              key={cell.isoDate}
              className={`commercial-ops-month__day ${cell.inCurrentPeriod ? '' : 'is-muted'}`}
              onClick={() => onSelectDay(cell.isoDate)}
            >
              <span className="commercial-ops-month__day-number">{getDayNumber(calendarMode, cell.isoDate)}</span>
              {totalsByCategory.length > 0 && (
                <span className="commercial-ops-month__day-markers">
                  {totalsByCategory.map((category) => (
                    <span key={category.key} className="commercial-ops-month__marker" style={{ background: category.color }} />
                  ))}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default MonthView
