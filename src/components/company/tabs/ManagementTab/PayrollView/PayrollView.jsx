import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import AddPositionModal from './AddPositionModal'
import PayrollTable from './PayrollTable'
import { useCloneSelection } from './useCloneSelection'
import { usePayrollData } from './usePayrollData'
import { fetchSettings } from '../../../../../services/settings'
import { subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import './PayrollView.css'

function PayrollView({ companyId: companyIdProp }) {
  const params = useParams()
  const companyId = companyIdProp ?? params.companyId
  const [isModalOpen, setModalOpen] = useState(false)
  const [selectedRowId, setSelectedRowId] = useState(null)
  const [editorValues, setEditorValues] = useState({
    officeName: '',
    employeeName: '',
    area: '',
    parentNodeId: '',
    yearSalary: '',
    startDate: '',
  })
  const [calendarMode, setCalendarMode] = useState('real')
  const {
    rows,
    loading,
    error,
    projectionYears,
    selectedYear,
    setSelectedYear,
    addPosition,
    savePosition,
    cloneSelected,
    deleteSelected,
  } = usePayrollData(companyId)
  const {
    cloneMode,
    deleteMode,
    selectedIds,
    toggleCloneMode,
    toggleDeleteMode,
    toggleSelected,
    reset,
  } = useCloneSelection()

  const selectedCount = useMemo(() => selectedIds.length, [selectedIds])
  const selectedRow = useMemo(
    () => rows.find((row) => row.node_id === selectedRowId) ?? null,
    [rows, selectedRowId],
  )

  const selectableParents = useMemo(
    () => rows.filter((row) => row.node_id !== selectedRowId),
    [rows, selectedRowId],
  )

  useEffect(() => {
    let cancelled = false

    const loadCalendarMode = async () => {
      try {
        const settings = await fetchSettings()
        if (!cancelled) {
          setCalendarMode(settings.calendar_mode ?? 'real')
        }
      } catch {
        if (!cancelled) {
          setCalendarMode('real')
        }
      }
    }

    loadCalendarMode()
    const unsubscribe = subscribeToCompanyDataChange(companyId, loadCalendarMode)

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [companyId])

  useEffect(() => {
    if (!selectedRow) {
      setEditorValues({
        officeName: '',
        employeeName: '',
        area: '',
        parentNodeId: '',
        yearSalary: '',
        startDate: '',
      })
      return undefined
    }

    setEditorValues({
      officeName: selectedRow.office_name || '',
      employeeName: selectedRow.employee_name || '',
      area: selectedRow.area || '',
      parentNodeId: selectedRow.parent_node_id || '',
      yearSalary: String(selectedRow.year_salary ?? ''),
      startDate: selectedRow.start_date || '',
    })
  }, [selectedRow])

  const defaultStartDate = getDefaultCalendarDate(calendarMode)

  const handleClone = async () => {
    await cloneSelected(selectedIds)
    reset()
  }

  const handleDelete = async () => {
    await deleteSelected(selectedIds)
    reset()
  }

  const handleSave = async () => {
    if (!selectedRowId) return

    await savePosition(selectedRowId, {
      office_name: editorValues.officeName,
      employee_name: editorValues.employeeName || null,
      area: editorValues.area || null,
      parent_node_id: editorValues.parentNodeId || null,
      year_salary: Number(editorValues.yearSalary),
      start_date: editorValues.startDate,
    })
  }

  return (
    <div className="payroll-view">
      <div className="payroll-view__toolbar">
        <label className="payroll-view__year-selector">
          Projection year
          <select
            value={selectedYear}
            onChange={(event) => setSelectedYear(Number(event.target.value))}
            aria-label="Select payroll projection year"
          >
            {Array.from({ length: projectionYears + 1 }, (_, index) => index).map((yearNumber) => (
              <option key={yearNumber} value={yearNumber}>
                Year {yearNumber}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="payroll-view__btn payroll-view__btn--primary"
          onClick={() => setModalOpen(true)}
        >
          + Add new position
        </button>
        <button type="button" className="payroll-view__btn" onClick={toggleCloneMode}>
          {cloneMode ? 'Cancel' : 'Clone position'}
        </button>
        <button type="button" className="payroll-view__btn payroll-view__btn--delete" onClick={toggleDeleteMode}>
          {deleteMode ? 'Cancel' : 'Delete position'}
        </button>
        {cloneMode && selectedCount > 0 ? (
          <button type="button" className="payroll-view__btn payroll-view__btn--clone" onClick={handleClone}>
            Clone ({selectedCount})
          </button>
        ) : null}
        {deleteMode && selectedCount > 0 ? (
          <button type="button" className="payroll-view__btn payroll-view__btn--delete-confirm" onClick={handleDelete}>
            Delete ({selectedCount})
          </button>
        ) : null}
      </div>

      <PayrollTable
        rows={rows}
        calendarMode={calendarMode}
        selectionMode={cloneMode || deleteMode}
        selectedIds={selectedIds}
        onToggleSelected={toggleSelected}
        selectedRowId={selectedRowId}
        onRowClick={(row) => {
          if (cloneMode || deleteMode) return
          setSelectedRowId(row.node_id)
        }}
      />

      {selectedRow ? (
        <section className="payroll-view__editor">
          <h4>Edit position</h4>
          <div className="payroll-view__editor-grid">
            <label>
              Position name
              <input
                type="text"
                value={editorValues.officeName}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, officeName: event.target.value }))}
              />
            </label>
            <label>
              Employee name
              <input
                type="text"
                value={editorValues.employeeName}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, employeeName: event.target.value }))}
              />
            </label>
            <label>
              Area
              <input
                type="text"
                value={editorValues.area}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, area: event.target.value }))}
              />
            </label>
            <label>
              Subordinated to
              <select
                value={editorValues.parentNodeId}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, parentNodeId: event.target.value }))}
              >
                <option value="">— Top of chart —</option>
                {selectableParents.map((position) => (
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
                value={editorValues.yearSalary}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, yearSalary: event.target.value }))}
              />
            </label>
            <label>
              Start date
              {calendarMode === 'simulation' ? (
                <SimulationDatePicker
                  value={editorValues.startDate}
                  onChange={(nextValue) => setEditorValues((prev) => ({ ...prev, startDate: nextValue }))}
                />
              ) : (
                <input
                  type="date"
                  value={editorValues.startDate}
                  onChange={(event) => setEditorValues((prev) => ({ ...prev, startDate: event.target.value }))}
                  aria-label="Start date"
                />
              )}
            </label>
          </div>
          <div className="payroll-view__editor-actions">
            <button type="button" className="payroll-view__btn payroll-view__btn--primary" onClick={handleSave}>
              Save
            </button>
            <button type="button" className="payroll-view__btn" onClick={() => setSelectedRowId(null)}>
              Close
            </button>
          </div>
        </section>
      ) : (
        <div className="payroll-view__status">Click a position to edit its details.</div>
      )}

      {loading && rows.length === 0 ? <div className="payroll-view__status">Loading payroll...</div> : null}
      {error && rows.length === 0 ? (
        <div className="payroll-view__status payroll-view__status--error">{error}</div>
      ) : null}

      {isModalOpen && (
        <AddPositionModal
          positions={rows}
          calendarMode={calendarMode}
          initialStartDate={defaultStartDate}
          selectedYear={selectedYear}
          onSave={async (values) => {
            await addPosition(values)
            setModalOpen(false)
          }}
          onCancel={() => setModalOpen(false)}
        />
      )}
    </div>
  )
}

export default PayrollView