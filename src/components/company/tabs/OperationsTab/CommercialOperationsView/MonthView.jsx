import { WEEKDAY_LABELS, getDayNumber, getMonthCells } from './calendarViewMath'
import { formatCategoryTooltip, sumByCategory } from './entryTotals'

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
          const totalsByCategory = sumByCategory(dayEntries)
          const nonZeroCategories = totalsByCategory.filter((category) => category.total > 0)

          return (
            <button
              type="button"
              key={cell.isoDate}
              className={`commercial-ops-month__day ${cell.inCurrentPeriod ? '' : 'is-muted'}`}
              onClick={() => onSelectDay(cell.isoDate)}
              title={dayEntries.length > 0 ? formatCategoryTooltip(dayEntries) : undefined}
            >
              <span className="commercial-ops-month__day-number">{getDayNumber(calendarMode, cell.isoDate)}</span>
              {nonZeroCategories.length > 0 && (
                <span className="commercial-ops-month__day-markers">
                  {nonZeroCategories.map((category) => (
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
