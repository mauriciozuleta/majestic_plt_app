import { useMemo, useState } from 'react'
import './PayrollTable.css'
import { formatCalendarDateCompact } from '../../../../../services/calendarDates'

function groupByArea(rows) {
  const groups = new Map()
  rows.forEach((row) => {
    const area = row.area || 'Unassigned'
    if (!groups.has(area)) groups.set(area, [])
    groups.get(area).push(row)
  })
  return groups
}

function PayrollTable({
  rows,
  selectionMode,
  selectedIds,
  onToggleSelected,
  selectedRowId,
  onRowClick,
  calendarMode,
  onDragStart,
  onDragEnd,
  onDropRow,
}) {
  const [collapsedAreas, setCollapsedAreas] = useState(() => new Set())

  const officeNameById = useMemo(() => {
    const map = new Map()
    rows.forEach((row) => map.set(row.node_id, row.office_name))
    return map
  }, [rows])

  const groups = useMemo(() => groupByArea(rows), [rows])
  const grandTotals = useMemo(
    () =>
      rows.reduce(
        (totals, row) => ({
          headcount: totals.headcount + (row.headcount ?? 1),
          monthly: totals.monthly + Number(row.monthly_salary || 0),
          year: totals.year + Number(row.year_salary || 0) * (row.headcount ?? 1),
        }),
        { headcount: 0, monthly: 0, year: 0 },
      ),
    [rows],
  )

  const toggleArea = (area) => {
    setCollapsedAreas((prev) => {
      const next = new Set(prev)
      if (next.has(area)) next.delete(area)
      else next.add(area)
      return next
    })
  }

  return (
    <div className="payroll-table">
      <div className="payroll-table__header">
        <div className="payroll-table__col payroll-table__col--check" />
        <div className="payroll-table__col payroll-table__col--name">Position</div>
        <div className="payroll-table__col">Area</div>
        <div className="payroll-table__col">Headcount</div>
        <div className="payroll-table__col">Year salary</div>
        <div className="payroll-table__col">Monthly salary</div>
        <div className="payroll-table__col">Start date</div>
      </div>

      {rows.length === 0 ? (
        <div className="payroll-table__empty">No payroll positions active for this year.</div>
      ) : (
        Array.from(groups.entries()).map(([area, members]) => {
          const collapsed = collapsedAreas.has(area)
          const subtotal = members.reduce(
            (totals, row) => ({
              headcount: totals.headcount + (row.headcount ?? 1),
              monthly: totals.monthly + Number(row.monthly_salary || 0),
              year: totals.year + Number(row.year_salary || 0) * (row.headcount ?? 1),
            }),
            { headcount: 0, monthly: 0, year: 0 },
          )

          return (
            <div key={area}>
              <div
                className={`payroll-table__group-header ${collapsed ? 'is-collapsed' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => toggleArea(area)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    toggleArea(area)
                  }
                }}
              >
                <span className="payroll-table__group-chevron">▾</span>
                {area}
                <span className="payroll-table__group-count">
                  {members.length} position{members.length === 1 ? '' : 's'}
                </span>
              </div>

              {!collapsed &&
                members.map((row) => (
                  <div
                    className={`payroll-table__row ${selectedIds.includes(row.node_id) ? 'is-selected' : ''} ${
                      selectedRowId === row.node_id ? 'is-active' : ''
                    }`}
                    key={row.node_id}
                    role="button"
                    tabIndex={0}
                    draggable={!selectionMode}
                    onClick={() => onRowClick?.(row)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onRowClick?.(row)
                      }
                    }}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'move'
                      event.dataTransfer.setData('text/plain', row.node_id)
                      onDragStart?.(row.node_id)
                    }}
                    onDragOver={(event) => {
                      if (!selectionMode) event.preventDefault()
                    }}
                    onDrop={(event) => {
                      if (selectionMode) return
                      event.preventDefault()
                      const sourceNodeId = event.dataTransfer.getData('text/plain') || row.node_id
                      onDropRow?.(sourceNodeId, row.node_id)
                    }}
                    onDragEnd={() => onDragEnd?.()}
                  >
                    <div className="payroll-table__col payroll-table__col--check">
                      {selectionMode ? (
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(row.node_id)}
                          onChange={() => onToggleSelected(row.node_id)}
                          onClick={(event) => event.stopPropagation()}
                        />
                      ) : (
                        <span className="payroll-table__drag-handle" aria-label="Drag to reorder" title="Drag to reorder">
                          ⋮⋮
                        </span>
                      )}
                    </div>
                    <div
                      className="payroll-table__col payroll-table__col--name"
                      title={row.headcount > 1 ? `${row.headcount} employees on this position` : 'Vacant position'}
                    >
                      {row.office_name}
                      <span className="payroll-table__reports-to">
                        {row.parent_node_id ? `reports to ${officeNameById.get(row.parent_node_id) || '—'}` : 'top of chart'}
                      </span>
                    </div>
                    <div className="payroll-table__col">{row.area || 'Unassigned'}</div>
                    <div className="payroll-table__col payroll-table__col--num" title={`${row.headcount ?? 1} active this year`}>
                      {row.headcount ?? 1}
                    </div>
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
                ))}

              {!collapsed && (
                <div className="payroll-table__subtotal-row">
                  <div className="payroll-table__col payroll-table__col--check" />
                  <div className="payroll-table__col payroll-table__col--name">{area} subtotal</div>
                  <div className="payroll-table__col" />
                  <div className="payroll-table__col payroll-table__col--num">{subtotal.headcount}</div>
                  <div className="payroll-table__col payroll-table__col--num">—</div>
                  <div className="payroll-table__col payroll-table__col--num">${subtotal.monthly.toLocaleString()}</div>
                  <div className="payroll-table__col" />
                </div>
              )}
            </div>
          )
        })
      )}

      {rows.length > 0 && (
        <div className="payroll-table__grand-row">
          <div className="payroll-table__col payroll-table__col--check" />
          <div className="payroll-table__col payroll-table__col--name">Grand total ({rows.length} positions)</div>
          <div className="payroll-table__col" />
          <div className="payroll-table__col payroll-table__col--num">{grandTotals.headcount}</div>
          <div className="payroll-table__col payroll-table__col--num">—</div>
          <div className="payroll-table__col payroll-table__col--num">${grandTotals.monthly.toLocaleString()}</div>
          <div className="payroll-table__col" />
        </div>
      )}
    </div>
  )
}

export default PayrollTable
