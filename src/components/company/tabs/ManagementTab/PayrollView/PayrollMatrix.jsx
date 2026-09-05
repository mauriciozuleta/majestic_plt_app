import { useMemo, useState } from 'react'
import AreaAutocomplete from './AreaAutocomplete'
import { employeeMonthlyActive, positionMonthlyHeadcount } from './monthMath'
import './PayrollMatrix.css'

const MONTH_LABELS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12']

function seatLabel(officeName, index) {
  return `${officeName} #${index + 1}`
}

function ParentSelect({ value, isDirty, onChange, allPositions, excludeNodeId }) {
  return (
    <select className={isDirty ? 'is-dirty' : ''} value={value || ''} onChange={(event) => onChange(event.target.value || null)}>
      <option value="">— Top of chart —</option>
      {allPositions
        .filter((position) => position.node_id !== excludeNodeId)
        .map((position) => (
          <option key={position.node_id} value={position.node_id}>
            {position.office_name}
          </option>
        ))}
    </select>
  )
}

function CompInput({ yearSalary, isDirty, onChange }) {
  return (
    <input
      type="number"
      min="0"
      step="500"
      className={`payroll-matrix__comp-input ${isDirty ? 'is-dirty' : ''}`}
      value={yearSalary}
      onChange={(event) => {
        const nextValue = Number(event.target.value)
        if (Number.isFinite(nextValue)) onChange(nextValue)
      }}
    />
  )
}

function MonthCells({ nodeId, months, draftMonths, onDraftMonthChange }) {
  const displayed = draftMonths || months
  return displayed.map((value, index) => (
    <td key={index} className="num">
      <input
        type="number"
        min="0"
        className={`payroll-matrix__month-input ${draftMonths ? 'is-dirty' : ''}`}
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value)
          onDraftMonthChange(nodeId, index, Number.isFinite(next) && next >= 0 ? next : 0, months)
        }}
      />
    </td>
  ))
}

function PayrollMatrix({
  rows,
  allPositions,
  areaOptions,
  selectedYear,
  calendarMode,
  headcountDrafts,
  onDraftMonthChange,
  onPositionClick,
  positionDrafts,
  employeeDrafts,
  onDraftPositionField,
  onDraftEmployeeField,
  onRemoveEmployee,
  selectionMode,
  selectedIds,
  onToggleSelected,
}) {
  const [collapsedIds, setCollapsedIds] = useState(() => new Set())

  const toggleCollapsed = (nodeId) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }

  const built = useMemo(
    () =>
      rows.map((row) => {
        const positionDraft = positionDrafts.get(row.node_id) || {}
        const effectiveParent = 'parent_node_id' in positionDraft ? positionDraft.parent_node_id : row.parent_node_id
        const effectiveArea = 'area' in positionDraft ? positionDraft.area : row.area
        const effectiveYearSalary = 'year_salary' in positionDraft ? positionDraft.year_salary : row.year_salary

        const employees = row.employees || []
        const totalMonths = positionMonthlyHeadcount(employees, selectedYear, calendarMode)
        const isSplit = Math.max(0, ...totalMonths) > 1
        const seats = isSplit
          ? [...employees]
              .sort((a, b) => String(a.start_date).localeCompare(String(b.start_date)))
              .map((employee, index) => {
                const employeeDraft = employeeDrafts.get(employee.id) || {}
                return {
                  employee,
                  label: seatLabel(row.office_name, index),
                  months: employeeMonthlyActive(employee, selectedYear, calendarMode),
                  effectiveReportsTo:
                    'reports_to_node_id' in employeeDraft ? employeeDraft.reports_to_node_id : employee.reports_to_node_id,
                  effectiveArea: 'area' in employeeDraft ? employeeDraft.area : employee.area,
                }
              })
          : []
        const displayMonths = headcountDrafts.get(row.node_id) || totalMonths
        const monthlyCost = displayMonths.map((headcount) => Math.round((effectiveYearSalary * headcount) / 12))
        const yearTotal = monthlyCost.reduce((sum, value) => sum + value, 0)
        return {
          row,
          totalMonths,
          isSplit,
          seats,
          monthlyCost,
          yearTotal,
          effectiveParent,
          effectiveArea,
          effectiveYearSalary,
          hasPositionDraft: positionDrafts.has(row.node_id),
        }
      }),
    [rows, selectedYear, calendarMode, headcountDrafts, positionDrafts, employeeDrafts],
  )

  const grandHeadcount = new Array(12).fill(0)
  const grandCost = new Array(12).fill(0)
  built.forEach(({ row, totalMonths, monthlyCost }) => {
    const displayMonths = headcountDrafts.get(row.node_id) || totalMonths
    displayMonths.forEach((v, i) => { grandHeadcount[i] += v })
    monthlyCost.forEach((v, i) => { grandCost[i] += v })
  })

  return (
    <div className="payroll-matrix">
      <div className="payroll-matrix__scroll-outer">
        <div className="payroll-matrix__panel">
          <div className="payroll-matrix__panel-title">Headcount by month — Year {selectedYear}</div>
          <div className="payroll-matrix__scroll">
            <table className="payroll-matrix__table">
              <thead>
                <tr>
                  <th className="sticky-col sticky-1">Position</th>
                  <th className="sticky-col sticky-2 num">Yearly comp</th>
                  <th className="sticky-col sticky-3">Reports To</th>
                  <th className="sticky-col sticky-4">Area</th>
                  {MONTH_LABELS.map((label) => (
                    <th key={label} className="num">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {built.length === 0 ? (
                  <tr><td colSpan={16} className="payroll-matrix__empty">No positions active in Year {selectedYear}.</td></tr>
                ) : (
                  built.flatMap(({ row, totalMonths, isSplit, seats, effectiveParent, effectiveArea, effectiveYearSalary, hasPositionDraft }) => {
                    const draftMonths = headcountDrafts.get(row.node_id) || null
                    const positionDraft = positionDrafts.get(row.node_id) || {}

                    if (!isSplit) {
                      return [
                        <tr key={row.node_id} className={selectionMode && selectedIds.includes(row.node_id) ? 'is-selected' : ''}>
                          <td className="sticky-col sticky-1">
                            {selectionMode && (
                              <input
                                type="checkbox"
                                className="payroll-matrix__select"
                                checked={selectedIds.includes(row.node_id)}
                                onChange={() => onToggleSelected(row.node_id)}
                              />
                            )}
                            <button
                              type="button"
                              className="payroll-matrix__position-link"
                              onClick={() => (selectionMode ? onToggleSelected(row.node_id) : onPositionClick(row))}
                            >
                              {row.office_name}
                            </button>
                          </td>
                          <td className="sticky-col sticky-2 num">
                            <CompInput
                              yearSalary={effectiveYearSalary}
                              isDirty={'year_salary' in positionDraft}
                              onChange={(nextValue) => onDraftPositionField(row.node_id, 'year_salary', nextValue)}
                            />
                          </td>
                          <td className="sticky-col sticky-3">
                            <ParentSelect
                              value={effectiveParent}
                              isDirty={'parent_node_id' in positionDraft}
                              excludeNodeId={row.node_id}
                              allPositions={allPositions}
                              onChange={(nextParentId) => onDraftPositionField(row.node_id, 'parent_node_id', nextParentId)}
                            />
                          </td>
                          <td className="sticky-col sticky-4">
                            <AreaAutocomplete
                              value={effectiveArea}
                              isDirty={'area' in positionDraft}
                              options={areaOptions}
                              onChange={(nextArea) => onDraftPositionField(row.node_id, 'area', nextArea)}
                              className="payroll-matrix__area-input"
                            />
                          </td>
                          <MonthCells nodeId={row.node_id} months={totalMonths} draftMonths={draftMonths} onDraftMonthChange={onDraftMonthChange} />
                        </tr>,
                      ]
                    }

                    const isCollapsed = collapsedIds.has(row.node_id)

                    const categoryRow = (
                      <tr
                        className={`payroll-matrix__category-row ${hasPositionDraft ? 'is-dirty' : ''} ${
                          selectionMode && selectedIds.includes(row.node_id) ? 'is-selected' : ''
                        }`}
                        key={`${row.node_id}-category`}
                      >
                        <td className="sticky-col sticky-1">
                          {selectionMode && (
                            <input
                              type="checkbox"
                              className="payroll-matrix__select"
                              checked={selectedIds.includes(row.node_id)}
                              onChange={() => onToggleSelected(row.node_id)}
                            />
                          )}
                          <button
                            type="button"
                            className="payroll-matrix__collapse-toggle"
                            title={isCollapsed ? 'Expand seats' : 'Collapse seats'}
                            onClick={() => toggleCollapsed(row.node_id)}
                          >
                            {isCollapsed ? '▸' : '▾'}
                          </button>
                          <button
                            type="button"
                            className="payroll-matrix__position-link"
                            onClick={() => (selectionMode ? onToggleSelected(row.node_id) : onPositionClick(row))}
                          >
                            {row.office_name}
                          </button>
                          <span className="payroll-matrix__category-tag">{seats.length} seats</span>
                        </td>
                        <td className="sticky-col sticky-2 num">
                          <CompInput
                            yearSalary={effectiveYearSalary}
                            isDirty={'year_salary' in positionDraft}
                            onChange={(nextValue) => onDraftPositionField(row.node_id, 'year_salary', nextValue)}
                          />
                        </td>
                        <td className="sticky-col sticky-3" />
                        <td className="payroll-matrix__category-spacer" colSpan={13} />
                      </tr>
                    )

                    const seatRows = seats.map(({ employee, label, months, effectiveReportsTo, effectiveArea: seatArea }) => {
                      const employeeDraft = employeeDrafts.get(employee.id) || {}
                      return (
                        <tr className="payroll-matrix__seat-row" key={employee.id}>
                          <td className="sticky-col sticky-1">
                            <div className="payroll-matrix__seat-name">
                              {label}
                              <button type="button" className="payroll-matrix__remove" title="Remove this seat" onClick={() => onRemoveEmployee(employee.id)}>×</button>
                            </div>
                          </td>
                          <td className="sticky-col sticky-2" />
                          <td className="sticky-col sticky-3">
                            <ParentSelect
                              value={effectiveReportsTo || effectiveParent}
                              isDirty={'reports_to_node_id' in employeeDraft}
                              excludeNodeId={row.node_id}
                              allPositions={allPositions}
                              onChange={(nextParentId) => onDraftEmployeeField(employee.id, 'reports_to_node_id', nextParentId)}
                            />
                          </td>
                          <td className="sticky-col sticky-4">
                            <AreaAutocomplete
                              value={seatArea || effectiveArea}
                              isDirty={'area' in employeeDraft}
                              options={areaOptions}
                              onChange={(nextArea) => onDraftEmployeeField(employee.id, 'area', nextArea)}
                              className="payroll-matrix__area-input"
                            />
                          </td>
                          {months.map((active, index) => (
                            <td key={index} className="num">{active ? 1 : '—'}</td>
                          ))}
                        </tr>
                      )
                    })

                    return isCollapsed ? [categoryRow] : [categoryRow, ...seatRows]
                  })
                )}
              </tbody>
              {built.length > 0 && (
                <tfoot>
                  <tr className="payroll-matrix__total-row">
                    <td className="sticky-col sticky-1" colSpan={4}>Total headcount</td>
                    {grandHeadcount.map((value, index) => (
                      <td key={index} className="num">{value}</td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>

        <div className="payroll-matrix__panel">
          <div className="payroll-matrix__panel-title">Payroll cost by month — Year {selectedYear} (computed)</div>
          <div className="payroll-matrix__scroll">
            <table className="payroll-matrix__table">
              <thead>
                <tr>
                  <th className="sticky-col sticky-1">Position</th>
                  {MONTH_LABELS.map((label) => (
                    <th key={label} className="num">{label}</th>
                  ))}
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {built.length === 0 ? (
                  <tr><td colSpan={14} className="payroll-matrix__empty">Nothing to cost out for Year {selectedYear}.</td></tr>
                ) : (
                  built.map(({ row, monthlyCost, yearTotal }) => (
                    <tr key={row.node_id}>
                      <td className="sticky-col sticky-1">{row.office_name}</td>
                      {monthlyCost.map((value, index) => (
                        <td key={index} className="num">${(value / 1000).toFixed(1)}k</td>
                      ))}
                      <td className="num">${yearTotal.toLocaleString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
              {built.length > 0 && (
                <tfoot>
                  <tr className="payroll-matrix__total-row">
                    <td className="sticky-col sticky-1">Total cost</td>
                    {grandCost.map((value, index) => (
                      <td key={index} className="num">${(value / 1000).toFixed(1)}k</td>
                    ))}
                    <td className="num">${grandCost.reduce((a, b) => a + b, 0).toLocaleString()}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PayrollMatrix
