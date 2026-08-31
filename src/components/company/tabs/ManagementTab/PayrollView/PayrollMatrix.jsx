import { useEffect, useMemo, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import './PayrollMatrix.css'

function PayrollMatrix({
  rows,
  selectedYear,
  calendarMode,
  onPositionClick,
  onAddEmployee,
  onUpdateEmployee,
  onRemoveEmployee,
}) {
  const [draft, setDraft] = useState({ nodeId: '', employeeName: '', startDate: getDefaultCalendarDate(calendarMode) })
  const [endDateEnabled, setEndDateEnabled] = useState(() => new Set())

  useEffect(() => {
    setDraft((prev) => ({ ...prev, startDate: getDefaultCalendarDate(calendarMode) }))
  }, [calendarMode])

  const hires = useMemo(() => {
    // Positions arrive pre-sorted (by whatever "Sort by" is selected) — keep that order,
    // only sorting each position's own hires by start date underneath it.
    const flat = []
    rows.forEach((row) => {
      const activeEmployees = (row.employees || [])
        .filter((employee) => {
          const startsOnOrBefore = (employee.start_projection_year ?? 0) <= selectedYear
          const stillActive = employee.end_projection_year == null || employee.end_projection_year >= selectedYear
          return startsOnOrBefore && stillActive
        })
        .sort((a, b) => String(a.start_date).localeCompare(String(b.start_date)))

      activeEmployees.forEach((employee) => flat.push({ employee, row }))
    })
    return flat
  }, [rows, selectedYear])

  const hasEndDate = (employee) => Boolean(employee.end_date) || endDateEnabled.has(employee.id)

  const toggleEndDate = (employee) => {
    if (hasEndDate(employee)) {
      setEndDateEnabled((prev) => {
        const next = new Set(prev)
        next.delete(employee.id)
        return next
      })
      if (employee.end_date) onUpdateEmployee(employee.id, { end_date: null, end_projection_year: null })
    } else {
      setEndDateEnabled((prev) => new Set(prev).add(employee.id))
    }
  }

  const handleAdd = () => {
    if (!draft.nodeId || !draft.startDate) return
    onAddEmployee(draft.nodeId, {
      employee_name: draft.employeeName.trim() || null,
      start_date: draft.startDate,
    })
    setDraft((prev) => ({ ...prev, employeeName: '' }))
  }

  return (
    <div className="payroll-matrix">
      <div className="payroll-matrix__toolbar">
        <label>
          Position
          <select value={draft.nodeId} onChange={(event) => setDraft((prev) => ({ ...prev, nodeId: event.target.value }))}>
            <option value="">Select a position…</option>
            {rows.map((row) => (
              <option key={row.node_id} value={row.node_id}>
                {row.office_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          New hire's name (optional)
          <input
            type="text"
            value={draft.employeeName}
            onChange={(event) => setDraft((prev) => ({ ...prev, employeeName: event.target.value }))}
            placeholder="Vacant"
          />
        </label>
        <label>
          Start date
          {calendarMode === 'simulation' ? (
            <SimulationDatePicker
              value={draft.startDate}
              onChange={(nextValue) => setDraft((prev) => ({ ...prev, startDate: nextValue }))}
            />
          ) : (
            <input
              type="date"
              value={draft.startDate}
              onChange={(event) => setDraft((prev) => ({ ...prev, startDate: event.target.value }))}
            />
          )}
        </label>
        <button type="button" className="payroll-view__btn payroll-view__btn--primary" onClick={handleAdd}>
          + Add employee
        </button>
      </div>

      <div className="payroll-matrix__table">
        <div className="payroll-matrix__header">
          <div>Position</div>
          <div>Employee</div>
          <div>Start</div>
          <div>End</div>
          <div className="payroll-matrix__col--num">Year salary (Year {selectedYear})</div>
          <div />
        </div>

        {hires.length === 0 ? (
          <div className="payroll-matrix__empty">No hires match Year {selectedYear} yet.</div>
        ) : (
          hires.map(({ employee, row }) => (
            <div className="payroll-matrix__row" key={employee.id}>
              <button type="button" className="payroll-matrix__position-link" onClick={() => onPositionClick(row)}>
                {row.office_name}
              </button>
              <input
                type="text"
                placeholder="Vacant"
                defaultValue={employee.employee_name || ''}
                onBlur={(event) => {
                  const nextName = event.target.value.trim() || null
                  if (nextName !== employee.employee_name) onUpdateEmployee(employee.id, { employee_name: nextName })
                }}
              />

              {calendarMode === 'simulation' ? (
                <SimulationDatePicker
                  value={employee.start_date}
                  onChange={(nextValue) => {
                    if (nextValue !== employee.start_date) onUpdateEmployee(employee.id, { start_date: nextValue })
                  }}
                />
              ) : (
                <input
                  type="date"
                  aria-label="Start date"
                  defaultValue={employee.start_date}
                  onBlur={(event) => {
                    if (event.target.value && event.target.value !== employee.start_date) {
                      onUpdateEmployee(employee.id, { start_date: event.target.value })
                    }
                  }}
                />
              )}

              {calendarMode === 'simulation' ? (
                <div className="payroll-matrix__end-cell">
                  <label className="payroll-matrix__end-toggle">
                    <input type="checkbox" checked={hasEndDate(employee)} onChange={() => toggleEndDate(employee)} />
                    Ends
                  </label>
                  {hasEndDate(employee) && (
                    <SimulationDatePicker
                      value={employee.end_date || getDefaultCalendarDate('simulation')}
                      onChange={(nextValue) => onUpdateEmployee(employee.id, { end_date: nextValue, end_projection_year: selectedYear })}
                    />
                  )}
                </div>
              ) : (
                <input
                  type="date"
                  aria-label="End date"
                  defaultValue={employee.end_date || ''}
                  onBlur={(event) => {
                    const nextEnd = event.target.value || null
                    if (nextEnd !== employee.end_date) {
                      onUpdateEmployee(employee.id, { end_date: nextEnd, end_projection_year: nextEnd ? selectedYear : null })
                    }
                  }}
                />
              )}

              <div className="payroll-matrix__col--num">${Number(row.year_salary).toLocaleString()}</div>
              <button type="button" className="payroll-matrix__remove" title="Remove this hire" onClick={() => onRemoveEmployee(employee.id)}>
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default PayrollMatrix
