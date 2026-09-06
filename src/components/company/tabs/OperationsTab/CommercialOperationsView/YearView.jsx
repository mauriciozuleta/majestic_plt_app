import { getMonthRange, getYearMonths } from './calendarViewMath'
import { entriesInRange, formatCategoryTooltip, sumByCategory } from './entryTotals'

function YearView({ calendarMode, referenceDate, entries, onSelectMonth }) {
  const months = getYearMonths(calendarMode, referenceDate)

  return (
    <div className="commercial-ops-year">
      {months.map((month) => {
        const { start, endExclusive } = getMonthRange(calendarMode, month.isoDate)
        const monthEntries = entriesInRange(entries, start, endExclusive)
        const totalsByCategory = sumByCategory(monthEntries)

        return (
          <button
            type="button"
            key={month.isoDate}
            className="commercial-ops-year__month"
            onClick={() => onSelectMonth(month.isoDate)}
            title={monthEntries.length > 0 ? formatCategoryTooltip(monthEntries) : undefined}
          >
            <span className="commercial-ops-year__month-label">{month.label}</span>
            <div className="commercial-ops-year__month-totals">
              {totalsByCategory.map((category) => (
                <span key={category.key} className="commercial-ops-year__month-total" style={{ color: category.color }}>
                  {category.label}: ${category.total.toLocaleString()}
                </span>
              ))}
            </div>
          </button>
        )
      })}
    </div>
  )
}

export default YearView
