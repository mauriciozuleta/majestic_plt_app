import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as XLSX from 'xlsx'
import AddPositionModal from './AddPositionModal'
import PayrollTable from './PayrollTable'
import PayrollMatrix from './PayrollMatrix'
import { useCloneSelection } from './useCloneSelection'
import { usePayrollData } from './usePayrollData'
import { fetchSettings } from '../../../../../services/settings'
import { broadcastCompanyDataChange, subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import { parseFlatTemplate } from './importUtils'
import { clusterResemblingAreas, pickCanonicalArea } from './areaUtils'
import { SORT_OPTIONS, sortPositions } from './positionSort'
import { addEmployee, createPosition, updatePosition } from '../../../../../services/payroll'
import {
  fetchPayrollTemplateFile,
  fetchPayrollTemplateStatus,
  generatePayrollTemplate,
} from '../../../../../services/payrollTemplate'
import './PayrollView.css'

const TEMPLATE_POLL_INTERVAL_MS = 3000

function PayrollView({ companyId: companyIdProp }) {
  const params = useParams()
  const navigate = useNavigate()
  const companyId = companyIdProp ?? params.companyId
  const [view, setView] = useState('structured')
  const [activeArea, setActiveArea] = useState(null)
  const [sortBy, setSortBy] = useState('level')
  const [isModalOpen, setModalOpen] = useState(false)
  const [templateState, setTemplateState] = useState('idle')
  const [templateMessage, setTemplateMessage] = useState('')
  const lastTemplateModifiedRef = useRef(null)
  const [selectedRowId, setSelectedRowId] = useState(null)
  const [editorValues, setEditorValues] = useState({
    officeName: '',
    area: '',
    parentNodeId: '',
    yearSalary: '',
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
    addRosterEmployee,
    saveRosterEmployee,
    removeRosterEmployee,
    reload,
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

  const areaCounts = useMemo(() => {
    const counts = new Map()
    rows.forEach((row) => {
      const area = row.area || 'Unassigned'
      counts.set(area, (counts.get(area) || 0) + 1)
    })
    return counts
  }, [rows])

  const filteredRows = useMemo(() => {
    const areaFiltered = activeArea === null ? rows : rows.filter((row) => (row.area || 'Unassigned') === activeArea)
    return sortPositions(areaFiltered, sortBy)
  }, [rows, activeArea, sortBy])

  const stats = useMemo(() => {
    const totals = filteredRows.reduce(
      (acc, row) => ({
        headcount: acc.headcount + (row.headcount ?? 1),
        monthly: acc.monthly + Number(row.monthly_salary || 0),
        year: acc.year + Number(row.year_salary || 0) * (row.headcount ?? 1),
      }),
      { headcount: 0, monthly: 0, year: 0 },
    )
    return { ...totals, positionCount: filteredRows.length }
  }, [filteredRows])

  const distinctAreas = useMemo(
    () => Array.from(new Set(rows.map((row) => row.area).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [rows],
  )

  const areaClusters = useMemo(
    () => clusterResemblingAreas(Array.from(areaCounts.keys())),
    [areaCounts],
  )

  const suspiciousAreas = useMemo(() => new Set(areaClusters.flat()), [areaClusters])

  const handleMergeAreas = async (cluster, canonicalArea) => {
    const affectedRows = rows.filter((row) => cluster.includes(row.area) && row.area !== canonicalArea)
    await Promise.all(affectedRows.map((row) => savePosition(row.node_id, { area: canonicalArea })))
    if (activeArea && cluster.includes(activeArea) && activeArea !== canonicalArea) {
      setActiveArea(canonicalArea)
    }
  }

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
        area: '',
        parentNodeId: '',
        yearSalary: '',
      })
      return undefined
    }

    setEditorValues({
      officeName: selectedRow.office_name || '',
      area: selectedRow.area || '',
      parentNodeId: selectedRow.parent_node_id || '',
      yearSalary: String(selectedRow.year_salary ?? ''),
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
      area: editorValues.area || null,
      parent_node_id: editorValues.parentNodeId || null,
      year_salary: Number(editorValues.yearSalary),
    })
  }

  const handleImportTemplate = async (positions) => {
    setTemplateState('importing')
    setTemplateMessage('Importing the saved template…')

    try {
      const nodeIdByName = new Map(rows.map((row) => [row.office_name, row.node_id]))
      const existingByName = new Map(rows.map((row) => [row.office_name, row]))

      for (const position of positions) {
        const existing = existingByName.get(position.name)

        if (existing) {
          const updates = {}
          if (position.area) updates.area = position.area
          if (position.compByYear[0]) updates.year_salary = position.compByYear[0]
          if (Object.keys(updates).length > 0) {
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(existing.node_id, updates, 0)
          }
          for (let yearIndex = 1; yearIndex < position.compByYear.length; yearIndex += 1) {
            if (!position.compByYear[yearIndex]) continue
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(existing.node_id, { year_salary: position.compByYear[yearIndex] }, yearIndex)
          }

          const existingHireKeys = new Set(
            (existing.employees || []).map((employee) => `${employee.employee_name || ''}|${employee.start_date}`),
          )
          for (const hire of position.employees) {
            const key = `${hire.employee_name || ''}|${hire.start_date}`
            if (existingHireKeys.has(key)) continue
            // eslint-disable-next-line no-await-in-loop
            await addEmployee(
              existing.node_id,
              { employee_name: hire.employee_name, start_date: hire.start_date || defaultStartDate, end_date: hire.end_date },
              0,
            )
          }
        } else {
          const [firstHire, ...remainingHires] = position.employees
          // eslint-disable-next-line no-await-in-loop
          const created = await createPosition(
            companyId,
            {
              office_name: position.name,
              employee_name: firstHire?.employee_name || null,
              area: position.area || null,
              parent_node_id: null,
              year_salary: position.compByYear[0] || 0,
              start_date: firstHire?.start_date || defaultStartDate,
            },
            0,
          )
          for (let yearIndex = 1; yearIndex < position.compByYear.length; yearIndex += 1) {
            if (!position.compByYear[yearIndex]) continue
            // eslint-disable-next-line no-await-in-loop
            await updatePosition(created.node_id, { year_salary: position.compByYear[yearIndex] }, yearIndex)
          }
          for (const hire of remainingHires) {
            // eslint-disable-next-line no-await-in-loop
            await addEmployee(
              created.node_id,
              { employee_name: hire.employee_name, start_date: hire.start_date || defaultStartDate, end_date: hire.end_date },
              0,
            )
          }
          nodeIdByName.set(position.name, created.node_id)
        }
      }

      // Second pass: every position (new or pre-existing) now has an id, so "Subordinated To"
      // can be wired up regardless of which order positions appeared in the sheet.
      for (const position of positions) {
        if (!position.parentName) continue
        const parentId = nodeIdByName.get(position.parentName)
        const childId = nodeIdByName.get(position.name)
        if (!parentId || !childId || parentId === childId) continue
        // eslint-disable-next-line no-await-in-loop
        await updatePosition(childId, { parent_node_id: parentId }, 0)
      }

      broadcastCompanyDataChange(companyId, 'payroll:import-template')
      await reload()
      setTemplateState('done')
      setTemplateMessage(`Imported ${positions.length} position${positions.length === 1 ? '' : 's'} from the saved template.`)
    } catch (err) {
      setTemplateState('error')
      setTemplateMessage(err.message || 'Something went wrong importing the template.')
    }
  }

  const handleDownloadFormat = async () => {
    setTemplateState('generating')
    setTemplateMessage('Opening a template in Excel…')
    try {
      const status = await generatePayrollTemplate(companyId)
      lastTemplateModifiedRef.current = status.modified_at
      setTemplateState('watching')
      setTemplateMessage("Template opened in Excel — fill it in, save (Ctrl+S), and this page will pick it up automatically.")
    } catch (err) {
      setTemplateState('error')
      setTemplateMessage(err.message || 'Could not generate the template.')
    }
  }

  useEffect(() => {
    if (templateState !== 'watching') return undefined

    const interval = setInterval(async () => {
      try {
        const status = await fetchPayrollTemplateStatus(companyId)
        if (!status.exists || status.modified_at === lastTemplateModifiedRef.current) return

        lastTemplateModifiedRef.current = status.modified_at
        const buffer = await fetchPayrollTemplateFile(companyId)
        const workbook = XLSX.read(buffer, { type: 'array' })
        const sheet = workbook.Sheets.Payroll || workbook.Sheets[workbook.SheetNames[0]]
        const jsonRows = XLSX.utils.sheet_to_json(sheet, { defval: '' })
        const parsed = parseFlatTemplate(jsonRows)

        if (parsed.positions.length === 0) {
          setTemplateMessage(parsed.warnings[0] || 'The saved file has no rows to import yet.')
          return
        }
        await handleImportTemplate(parsed.positions)
      } catch {
        // Transient poll failure (e.g. Excel still mid-save) — try again next tick.
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, TEMPLATE_POLL_INTERVAL_MS)

    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateState, companyId])

  const handleRowReorder = async (fromNodeId, toNodeId) => {
    if (!fromNodeId || !toNodeId || fromNodeId === toNodeId) return

    const currentOrder = [...rows]
    const fromIndex = currentOrder.findIndex((row) => row.node_id === fromNodeId)
    const toIndex = currentOrder.findIndex((row) => row.node_id === toNodeId)
    if (fromIndex === -1 || toIndex === -1) return

    const reordered = [...currentOrder]
    const [movedNode] = reordered.splice(fromIndex, 1)
    reordered.splice(toIndex, 0, movedNode)

    const nextOrder = reordered.map((row, index) => ({
      node_id: row.node_id,
      sort_index: (index + 1) * 10,
    }))

    await Promise.all(nextOrder.map((entry) => updatePosition(entry.node_id, { sort_index: entry.sort_index })))
    broadcastCompanyDataChange(companyId, 'payroll:reorder-position')
    await reload()
  }

  return (
    <div className="payroll-view">
      <datalist id="payroll-area-options">
        {distinctAreas.map((area) => (
          <option key={area} value={area} />
        ))}
      </datalist>

      <div className="payroll-view__stats">
        <div className="payroll-view__stat-tile">
          <div className="payroll-view__stat-label">Headcount (Year {selectedYear})</div>
          <div className="payroll-view__stat-value">{stats.headcount.toLocaleString()}</div>
          <div className="payroll-view__stat-sub">
            {stats.positionCount} position{stats.positionCount === 1 ? '' : 's'} shown
          </div>
        </div>
        <div className="payroll-view__stat-tile">
          <div className="payroll-view__stat-label">Monthly run-rate</div>
          <div className="payroll-view__stat-value">${Math.round(stats.monthly).toLocaleString()}</div>
          <div className="payroll-view__stat-sub">at current headcount</div>
        </div>
        <div className="payroll-view__stat-tile">
          <div className="payroll-view__stat-label">Year {selectedYear} total cost</div>
          <div className="payroll-view__stat-value">${Math.round(stats.year).toLocaleString()}</div>
          <div className="payroll-view__stat-sub">comp × headcount, summed</div>
        </div>
      </div>

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
        <label className="payroll-view__year-selector">
          Sort by
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} aria-label="Sort positions by">
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div className="payroll-view__view-toggle">
          <button type="button" className={view === 'structured' ? 'is-active' : ''} onClick={() => setView('structured')}>
            Structured
          </button>
          <button type="button" className={view === 'matrix' ? 'is-active' : ''} onClick={() => setView('matrix')}>
            Matrix
          </button>
        </div>
        <button
          type="button"
          className="payroll-view__btn"
          onClick={() => navigate(`/company/${companyId}/management/org-chart`)}
        >
          Org Chart
        </button>

        <button
          type="button"
          className="payroll-view__btn payroll-view__btn--primary"
          onClick={() => setModalOpen(true)}
        >
          + Add new position
        </button>
        <button
          type="button"
          className="payroll-view__btn"
          onClick={handleDownloadFormat}
          disabled={templateState === 'generating' || templateState === 'importing'}
        >
          {templateState === 'generating' ? 'Opening…' : 'Download format'}
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

      {templateState !== 'idle' && (
        <div
          className={`payroll-view__template-status ${
            templateState === 'error' ? 'is-error' : templateState === 'done' ? 'is-done' : ''
          }`}
        >
          <span>{templateMessage}</span>
          {templateState === 'watching' && <span className="payroll-view__template-spinner" aria-hidden="true" />}
          {(templateState === 'done' || templateState === 'error') && (
            <button type="button" className="payroll-view__btn" onClick={() => setTemplateState('idle')}>
              Dismiss
            </button>
          )}
        </div>
      )}

      {areaClusters.length > 0 && (
        <div className="payroll-view__area-warning">
          <span className="payroll-view__area-warning-icon">⚠</span>
          <div className="payroll-view__area-warning-body">
            {areaClusters.map((cluster) => {
              const canonicalArea = pickCanonicalArea(cluster, areaCounts)
              const otherSpellings = cluster.filter((area) => area !== canonicalArea)
              return (
                <div className="payroll-view__area-warning-row" key={cluster.join('|')}>
                  <span>
                    {otherSpellings.map((area, index) => (
                      <span key={area}>
                        {index > 0 ? ', ' : ''}
                        <b>"{area}"</b>
                      </span>
                    ))}{' '}
                    look{otherSpellings.length === 1 ? 's' : ''} like the same area as <b>"{canonicalArea}"</b> — probably a
                    typo, not a new area.
                  </span>
                  <button
                    type="button"
                    className="payroll-view__btn payroll-view__btn--primary"
                    onClick={() => handleMergeAreas(cluster, canonicalArea)}
                  >
                    Merge into "{canonicalArea}"
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="payroll-view__chip-row">
        <button
          type="button"
          className={`payroll-view__chip ${activeArea === null ? 'is-active' : ''}`}
          onClick={() => setActiveArea(null)}
        >
          All areas
        </button>
        {Array.from(areaCounts.entries()).map(([area, count]) => (
          <button
            key={area}
            type="button"
            className={`payroll-view__chip ${activeArea === area ? 'is-active' : ''} ${
              suspiciousAreas.has(area) ? 'is-suspicious' : ''
            }`}
            onClick={() => setActiveArea((prev) => (prev === area ? null : area))}
            title={suspiciousAreas.has(area) ? 'This area name looks similar to another one — see the warning above' : undefined}
          >
            {area}
            <span className="payroll-view__chip-count">{count}</span>
          </button>
        ))}
      </div>

      {view === 'structured' ? (
        <PayrollTable
          rows={filteredRows}
          calendarMode={calendarMode}
          selectionMode={cloneMode || deleteMode}
          selectedIds={selectedIds}
          onToggleSelected={toggleSelected}
          selectedRowId={selectedRowId}
          onRowClick={(row) => {
            if (cloneMode || deleteMode) return
            setSelectedRowId(row.node_id)
          }}
          onDropRow={handleRowReorder}
        />
      ) : (
        <PayrollMatrix
          rows={filteredRows}
          selectedYear={selectedYear}
          calendarMode={calendarMode}
          onPositionClick={(row) => setSelectedRowId(row.node_id)}
          onAddEmployee={(nodeId, employee) => addRosterEmployee(nodeId, employee)}
          onUpdateEmployee={(employeeId, updates) => saveRosterEmployee(employeeId, updates)}
          onRemoveEmployee={(employeeId) => removeRosterEmployee(employeeId)}
        />
      )}

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
              Area
              <input
                type="text"
                value={editorValues.area}
                onChange={(event) => setEditorValues((prev) => ({ ...prev, area: event.target.value }))}
                list="payroll-area-options"
                placeholder="Pick or type an area"
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
          </div>
          <div className="payroll-view__editor-actions">
            <button type="button" className="payroll-view__btn payroll-view__btn--primary" onClick={handleSave}>
              Save
            </button>
            <button type="button" className="payroll-view__btn" onClick={() => setSelectedRowId(null)}>
              Close
            </button>
          </div>

          <p className="payroll-view__roster-hint">
            {selectedRow.headcount} {selectedRow.headcount === 1 ? 'employee' : 'employees'} active in Year {selectedYear} —
            manage who's on this position, and their start/end dates, from the <b>Matrix</b> view.
          </p>
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