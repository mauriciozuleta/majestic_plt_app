import './PayrollTable.css'
import { formatCalendarDateCompact } from '../../../../../services/calendarDates'

function PayrollTable({ rows, selectionMode, selectedIds, onToggleSelected, selectedRowId, onRowClick, calendarMode }) {
  return (
    <div className="payroll-table">
      <div className="payroll-table__header">
        <div className="payroll-table__col payroll-table__col--check" />
        <div className="payroll-table__col payroll-table__col--name">Position</div>
        <div className="payroll-table__col">Area</div>
        <div className="payroll-table__col">Year salary</div>
        <div className="payroll-table__col">Monthly salary</div>
        <div className="payroll-table__col">Start date</div>
      </div>

      {rows.length === 0 ? (
        <div className="payroll-table__empty">No payroll positions yet.</div>
      ) : (
        rows.map((row) => (
          <div
            className={`payroll-table__row ${selectedIds.includes(row.node_id) ? 'is-selected' : ''} ${
              selectedRowId === row.node_id ? 'is-active' : ''
            }`}
            key={row.node_id}
            role="button"
            tabIndex={0}
            onClick={() => onRowClick?.(row)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onRowClick?.(row)
              }
            }}
          >
            <div className="payroll-table__col payroll-table__col--check">
              {selectionMode ? (
                <input
                  type="checkbox"
                  checked={selectedIds.includes(row.node_id)}
                  onChange={() => onToggleSelected(row.node_id)}
                  onClick={(event) => event.stopPropagation()}
                />
              ) : null}
            </div>
            <div
              className="payroll-table__col payroll-table__col--name"
              style={{ paddingLeft: `${12 + row.level * 20}px` }}
              title={row.employee_name ? `Employee: ${row.employee_name}` : 'Vacant position'}
            >
              {row.office_name}
            </div>
            <div className="payroll-table__col">{row.area || 'Unassigned'}</div>
            <div className="payroll-table__col payroll-table__col--num">
              ${Number(row.year_salary).toLocaleString()}
            </div>
            <div className="payroll-table__col payroll-table__col--num payroll-table__col--muted">
              ${Number(row.monthly_salary).toLocaleString()}
            </div>
            <div className="payroll-table__col payroll-table__col--num">
              {formatCalendarDateCompact(row.start_date, calendarMode)}
            </div>
          </div>
        ))
      )}
    </div>
  )
}

export default PayrollTable