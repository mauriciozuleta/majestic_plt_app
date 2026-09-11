import { useMemo } from 'react'
import { usePayrollCurrencyRates } from '../../../../../hooks/usePayrollCurrencyRates'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { formatLocalCurrencyForLocation } from '../../../../../utils/payrollLocalCurrency'
import './PayrollTable.css'

function formatUsd(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// The Structured view is a simple "position catalog": what positions exist
// and what each one pays — not the org hierarchy (Reports To), not location/
// area, not per-seat start dates. Those all already live in the Matrix view,
// which is where headcount, reporting lines, and comp are actually edited.
// So positions sharing a name AND the exact same year salary collapse into
// one row here — e.g. seven "Secretary / Assistant" seats that all pay the
// same show once, since all a viewer needs from this view is "what does a
// Secretary / Assistant make." Two seats with the same name but different
// pay stay as two separate rows, since that's a real difference this view
// exists to surface.
function groupByNameAndSalary(rows) {
  const groups = new Map()
  rows.forEach((row) => {
    const key = `${row.office_name}::${row.year_salary}::${row.location || ''}`
    const existing = groups.get(key)
    if (existing) {
      existing.nodeIds.push(row.node_id)
    } else {
      groups.set(key, {
        node_id: row.node_id,
        office_name: row.office_name,
        year_salary: row.year_salary,
        monthly_salary: row.monthly_salary,
        location: row.location,
        nodeIds: [row.node_id],
      })
    }
  })
  return Array.from(groups.values())
}

function PayrollTable({ rows, selectionMode, selectedIds, onToggleSelected, selectedRowId, onRowClick }) {
  const groups = useMemo(() => groupByNameAndSalary(rows), [rows])
  const rates = usePayrollCurrencyRates()

  const handleGroupToggle = (group) => {
    const allSelected = group.nodeIds.every((id) => selectedIds.includes(id))
    const target = !allSelected
    group.nodeIds.forEach((id) => {
      if (selectedIds.includes(id) !== target) onToggleSelected(id)
    })
  }

  return (
    <div className="payroll-table">
      {/* This scroll region is deliberately self-contained (its own
          max-height + overflow-y, not a slice of the page's own scroll) —
          the alternative of relying on an ancestor container's scroll
          budget is exactly what silently broke before: a stale viewport-
          height estimate a few components up meant most rows were simply
          unreachable, with no scrollbar ever appearing for them. */}
      <div className="payroll-table__scroll">
        <div className="payroll-table__header">
          <div className="payroll-table__col payroll-table__col--check" />
          <div className="payroll-table__col payroll-table__col--name">Position</div>
          <div className="payroll-table__col">Year salary</div>
          <div className="payroll-table__col">Monthly salary</div>
        </div>

        {groups.length === 0 ? (
          <div className="payroll-table__empty">No payroll positions yet.</div>
        ) : (
          groups.map((group) => {
            const allSelected = group.nodeIds.every((id) => selectedIds.includes(id))
            const someSelected = !allSelected && group.nodeIds.some((id) => selectedIds.includes(id))
            return (
              <div
                className={`payroll-table__row ${allSelected || someSelected ? 'is-selected' : ''} ${
                  group.nodeIds.includes(selectedRowId) ? 'is-active' : ''
                }`}
                key={`${group.office_name}::${group.year_salary}`}
                role="button"
                tabIndex={0}
                onClick={() => onRowClick?.(group)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onRowClick?.(group)
                  }
                }}
              >
                <div className="payroll-table__col payroll-table__col--check">
                  {selectionMode ? (
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected
                      }}
                      onChange={() => handleGroupToggle(group)}
                      onClick={(event) => event.stopPropagation()}
                    />
                  ) : null}
                </div>
                <div className="payroll-table__col payroll-table__col--name" title={group.nodeIds.length > 1 ? `${group.nodeIds.length} seats` : undefined}>
                  {group.office_name}
                  {group.nodeIds.length > 1 && <span className="payroll-table__seat-count">×{group.nodeIds.length}</span>}
                </div>
                <div className="payroll-table__col payroll-table__col--num payroll-table__col--stacked">
                  <span>{formatUsd(group.year_salary)}</span>
                  {formatLocalCurrencyForLocation(group.location, group.year_salary, rates) && (
                    <span className="payroll-table__local-currency">
                      {formatLocalCurrencyForLocation(group.location, group.year_salary, rates)}
                    </span>
                  )}
                </div>
                <div className="payroll-table__col payroll-table__col--num payroll-table__col--muted payroll-table__col--stacked">
                  <span>{formatUsd(group.monthly_salary)}</span>
                  {formatLocalCurrencyForLocation(group.location, group.monthly_salary, rates) && (
                    <span className="payroll-table__local-currency">
                      {formatLocalCurrencyForLocation(group.location, group.monthly_salary, rates)}
                    </span>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default PayrollTable
