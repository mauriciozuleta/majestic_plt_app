import './YearSummaryTable.css'

const defaultFormat = (value) => Math.round(value).toLocaleString()

function YearSummaryTable({ years, rows, formatValue = defaultFormat, nameHeader = 'Name' }) {
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
                {row.totalsByYear.map((value, index) => (
                  <td key={index} className="num">
                    {formatValue(value)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
        {rows.length > 0 && (
          <tfoot>
            <tr className="year-summary-table__total-row">
              <td className="sticky-col">Total</td>
              {grandTotals.map((value, index) => (
                <td key={index} className="num">
                  {formatValue(value)}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

export default YearSummaryTable
