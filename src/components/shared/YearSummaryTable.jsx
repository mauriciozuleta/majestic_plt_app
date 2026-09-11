import './YearSummaryTable.css'

const defaultFormat = (value) => Math.round(value).toLocaleString()

function asParts(value) {
  if (!value) return []
  return Array.isArray(value) ? value.filter(Boolean) : [value]
}

// formatSubValue/formatTotalSubValue are optional — when provided, they add
// a small subtitle line under a cell's main value (e.g. a local-currency
// equivalent for a non-USD position/category). Returning null/undefined
// skips the subtitle for that cell; returning an array renders one line
// per entry (e.g. multiple currencies contributing to one total).
function YearSummaryTable({ years, rows, formatValue = defaultFormat, formatSubValue, formatTotalSubValue, nameHeader = 'Name' }) {
  const grandTotals = years.map((_, yearIndex) => rows.reduce((sum, row) => sum + (row.totalsByYear[yearIndex] || 0), 0))

  return (
    <div className="year-summary-table__scroll">
      <table className="year-summary-table">
        <thead>
          <tr>
            <th className="sticky-col">{nameHeader}</th>
            {years.map((year) => (
              <th key={year} className="num">
                Year {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={years.length + 1} className="year-summary-table__empty">
                Nothing to summarize yet.
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.label}>
                <td className="sticky-col">{row.label}</td>
                {row.totalsByYear.map((value, index) => {
                  const subParts = asParts(formatSubValue?.(row, value, index))
                  return (
                    <td key={index} className={`num ${subParts.length ? 'year-summary-table__col--stacked' : ''}`}>
                      <span>{formatValue(value)}</span>
                      {subParts.map((part) => (
                        <span key={part} className="year-summary-table__local-currency">
                          {part}
                        </span>
                      ))}
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
        {rows.length > 0 && (
          <tfoot>
            <tr className="year-summary-table__total-row">
              <td className="sticky-col">Total</td>
              {grandTotals.map((value, index) => {
                const subParts = asParts(formatTotalSubValue?.(value, index))
                return (
                  <td key={index} className={`num ${subParts.length ? 'year-summary-table__col--stacked' : ''}`}>
                    <span>{formatValue(value)}</span>
                    {subParts.map((part) => (
                      <span key={part} className="year-summary-table__local-currency">
                        {part}
                      </span>
                    ))}
                  </td>
                )
              })}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

export default YearSummaryTable
