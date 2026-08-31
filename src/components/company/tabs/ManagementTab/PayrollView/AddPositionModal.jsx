import { useEffect, useMemo, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'

function AddPositionModal({ positions, onSave, onCancel, initialStartDate, calendarMode, selectedYear = 0 }) {
  const [officeName, setOfficeName] = useState('')
  const [employeeName, setEmployeeName] = useState('')
  const [area, setArea] = useState('')
  const [parentNodeId, setParentNodeId] = useState('')
  const [yearSalary, setYearSalary] = useState('')
  const [startDate, setStartDate] = useState(() => initialStartDate ?? new Date().toISOString().slice(0, 10))
  const [error, setError] = useState('')

  useEffect(() => {
    if (selectedYear < 0) {
      setStartDate(initialStartDate ?? new Date().toISOString().slice(0, 10))
    }
  }, [selectedYear, initialStartDate])

  useEffect(() => {
    if (initialStartDate) {
      setStartDate(initialStartDate)
    }
  }, [initialStartDate])

  const monthlySalary = useMemo(() => {
    const value = Number(yearSalary)
    if (!Number.isFinite(value) || value <= 0) return '0.00'
    return (value / 12).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  }, [yearSalary])

  const handleSubmit = async (event) => {
    event.preventDefault()

    const trimmedOfficeName = officeName.trim()
    const parsedSalary = Number(yearSalary)

    if (!trimmedOfficeName) {
      setError('Position name is required.')
      return
    }
    if (!Number.isFinite(parsedSalary) || parsedSalary <= 0) {
      setError('Year salary must be greater than 0.')
      return
    }
    if (!startDate) {
      setError('Start date is required.')
      return
    }

    await onSave({
      office_name: trimmedOfficeName,
      employee_name: employeeName.trim() || null,
      area: area.trim() || null,
      parent_node_id: parentNodeId || null,
      year_salary: parsedSalary,
      start_date: startDate,
    })
  }

  return (
    <div className="payroll-modal__overlay" onClick={onCancel}>
      <div className="payroll-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Add new position</h3>
        <form className="payroll-modal__form" onSubmit={handleSubmit}>
          <label>
            Position name
            <input
              type="text"
              value={officeName}
              onChange={(event) => setOfficeName(event.target.value)}
              placeholder="Head of Finance"
            />
          </label>
          <label>
            Employee name (optional)
            <input
              type="text"
              value={employeeName}
              onChange={(event) => setEmployeeName(event.target.value)}
              placeholder="Maria Zuleta"
            />
          </label>
          <label>
            Area
            <input
              type="text"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              placeholder="Pick or type an area"
              list="payroll-area-options"
            />
          </label>
          <label>
            Subordinated to
            <select value={parentNodeId} onChange={(event) => setParentNodeId(event.target.value)}>
              <option value="">— Top of chart —</option>
              {positions.map((position) => (
                <option key={position.node_id} value={position.node_id}>
                  {position.office_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Year salary (Year {selectedYear})
            <input
              type="number"
              min="0"
              step="0.01"
              value={yearSalary}
              onChange={(event) => setYearSalary(event.target.value)}
              placeholder="120000"
            />
          </label>
          <label>
            Monthly salary
            <input type="text" value={`$${monthlySalary}`} readOnly />
          </label>
          <label>
            Start date
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={startDate} onChange={setStartDate} />
            ) : (
              <input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                aria-label="Start date"
              />
            )}
          </label>

          {error && <div className="payroll-modal__error">{error}</div>}

          <div className="payroll-modal__actions">
            <button type="button" className="payroll-modal__cancel" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="payroll-modal__save">
              Save position
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddPositionModal