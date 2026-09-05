import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AddPositionModal from './AddPositionModal'
import AreaAutocomplete from './AreaAutocomplete'
import PayrollTable from './PayrollTable'
import PayrollMatrix from './PayrollMatrix'
import FileUploadButton from '../../../../shared/FileUploadButton'
import { useCloneSelection } from './useCloneSelection'
import { usePayrollData } from './usePayrollData'
import { useHeadcountDrafts } from './useHeadcountDrafts'
import { useMatrixFieldDrafts } from './useMatrixFieldDrafts'
import { useTemplateImport } from './useTemplateImport'
import { fetchSettings } from '../../../../../services/settings'
import { broadcastCompanyDataChange, subscribeToCompanyDataChange } from '../../../../../services/companyDataSync'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import { clusterResemblingAreas, pickCanonicalArea } from './areaUtils'
import { SORT_OPTIONS, sortPositions } from './positionSort'
import { updatePosition } from '../../../../../services/payroll'
import './PayrollView.css'

function PayrollView({ companyId: companyIdProp }) {
  const params = useParams()
  const navigate = useNavigate()
  const companyId = companyIdProp ?? params.companyId
  const [view, setView] = useState('structured')
  const [activeArea, setActiveArea] = useState(null)
  const [sortBy, setSortBy] = useState('level')
  const [isModalOpen, setModalOpen] = useState(false)
  const [selectedRowId, setSelectedRowId] = useState(null)
  const [editorValues, setEditorValues] = useState({ officeName: '', area: '' })
  const [calendarMode, setCalendarMode] = useState('real')
  const [defaultRaisePct, setDefaultRaisePct] = useState('')
  const [defaultRaiseStatus, setDefaultRaiseStatus] = useState('idle')
  const {
    rows,
    areas,
    loading,
    error,
    projectionYears,
    selectedYear,
    setSelectedYear,
    addPosition,
    savePosition,
    cloneSelected,
    deleteSelected,
    removeRosterEmployee,
    growAllPositionsSalary,
    clearAllPositionsSalaryRaise,
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

  // null = no raise applied to any position this year, a number = every position
  // shares that rate (the normal case, since "Apply to all" is the only way to
  // set it), undefined = positions disagree (e.g. one was added after the raise).
  const appliedDefaultRaise = useMemo(() => {
    if (rows.length === 0) return null
    const rates = new Set(rows.map((row) => row.growth_rate_pct ?? null))
    return rates.size === 1 ? [...rates][0] : undefined
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

  const distinctAreas = areas

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
      setEditorValues({ officeName: '', area: '' })
      return undefined
    }

    setEditorValues({
      officeName: selectedRow.office_name || '',
      area: selectedRow.area || '',
    })
  }, [selectedRow])

  const defaultStartDate = getDefaultCalendarDate(calendarMode)

  const { headcountDrafts, savingHeadcount, handleDraftMonthChange, handleDiscardHeadcountDrafts, handleSaveHeadcountDrafts } =
    useHeadcountDrafts({ companyId, rows, selectedYear, calendarMode, reload })

  const {
    positionDrafts,
    employeeDrafts,
    draftCount: fieldDraftCount,
    savingFieldDrafts,
    draftPositionField,
    draftEmployeeField,
    discardFieldDrafts,
    saveFieldDrafts,
  } = useMatrixFieldDrafts({ companyId, selectedYear, reload })

  const { templateState, templateMessage, handleDownloadFormat, handleUploadFormat, dismissTemplateStatus } = useTemplateImport({
    companyId,
    rows,
    defaultStartDate,
    reload,
  })

  const handleClone = async () => {
    await cloneSelected(selectedIds, defaultStartDate)
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
    })
  }

  const handleRemoveEmployee = (employeeId) => removeRosterEmployee(employeeId)

  const savingMatrixDrafts = savingHeadcount || savingFieldDrafts
  const totalMatrixDrafts = headcountDrafts.size + fieldDraftCount

  const handleSaveMatrixDrafts = async () => {
    await Promise.all([
      headcountDrafts.size > 0 ? handleSaveHeadcountDrafts() : null,
      fieldDraftCount > 0 ? saveFieldDrafts() : null,
    ])
  }

  const handleDiscardMatrixDrafts = () => {
    handleDiscardHeadcountDrafts()
    discardFieldDrafts()
  }

  useEffect(() => {
    if (appliedDefaultRaise === undefined) return
    setDefaultRaisePct(appliedDefaultRaise != null ? String(appliedDefaultRaise) : '')
    setDefaultRaiseStatus('idle')
  }, [appliedDefaultRaise, selectedYear])

  const isDefaultRaiseApplied =
    defaultRaiseStatus !== 'applying' &&
    appliedDefaultRaise != null &&
    defaultRaisePct !== '' &&
    String(appliedDefaultRaise) === String(Number(defaultRaisePct))

  const handleClearDefaultRaise = async () => {
    setDefaultRaiseStatus('applying')
    try {
      await clearAllPositionsSalaryRaise()
      setDefaultRaisePct('')
      setDefaultRaiseStatus('idle')
    } catch {
      setDefaultRaiseStatus('error')
    }
  }

  const handleApplyDefaultRaise = async () => {
    const parsed = Number(defaultRaisePct)
    if (!Number.isFinite(parsed) || parsed === 0) return
    setDefaultRaiseStatus('applying')
    try {
      await growAllPositionsSalary(parsed)
      setDefaultRaiseStatus('idle')
    } catch {
      setDefaultRaiseStatus('error')
    }
  }

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
          Default raise (Year {selectedYear})
          <div className="payroll-view__default-raise">
            <input
              type="number"
              step="0.5"
              className="payroll-view__default-raise-input"
              placeholder="%/yr"
              value={defaultRaisePct}
              onChange={(event) => {
                setDefaultRaisePct(event.target.value)
                setDefaultRaiseStatus('idle')
              }}
            />
            <button
              type="button"
              className={`payroll-view__btn ${isDefaultRaiseApplied ? 'payroll-view__btn--primary' : ''}`}
              disabled={!defaultRaisePct || defaultRaiseStatus === 'applying'}
              onClick={handleApplyDefaultRaise}
            >
              {defaultRaiseStatus === 'applying' ? 'Applying…' : isDefaultRaiseApplied ? 'Applied' : 'Apply to all'}
            </button>
            {appliedDefaultRaise != null && selectedYear > 0 && (
              <button
                type="button"
                className="payroll-view__btn"
                disabled={defaultRaiseStatus === 'applying'}
                onClick={handleClearDefaultRaise}
              >
                Clear
              </button>
            )}
          </div>
        </label>
        {defaultRaiseStatus === 'error' && <span className="payroll-view__default-raise-status is-error">Failed</span>}
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
          disabled={templateState === 'downloading' || templateState === 'importing'}
        >
          {templateState === 'downloading' ? 'Preparing…' : 'Download format'}
        </button>
        <FileUploadButton
          label={templateState === 'importing' ? 'Importing…' : 'Upload filled format'}
          accept=".xlsx"
          disabled={templateState === 'downloading' || templateState === 'importing'}
          className="payroll-view__btn"
          onFileSelected={handleUploadFormat}
        />
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
          {(templateState === 'done' || templateState === 'error') && (
            <button type="button" className="payroll-view__btn" onClick={dismissTemplateStatus}>
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
            setView('matrix')
          }}
          onDropRow={handleRowReorder}
        />
      ) : (
        <>
          {totalMatrixDrafts > 0 && (
            <div className="payroll-view__template-status">
              <span>
                {totalMatrixDrafts} unsaved change{totalMatrixDrafts === 1 ? '' : 's'} — the org chart won't reflect these until you save.
              </span>
              <span style={{ display: 'flex', gap: '0.5rem' }}>
                <button type="button" className="payroll-view__btn" onClick={handleDiscardMatrixDrafts} disabled={savingMatrixDrafts}>
                  Discard
                </button>
                <button
                  type="button"
                  className="payroll-view__btn payroll-view__btn--primary"
                  onClick={handleSaveMatrixDrafts}
                  disabled={savingMatrixDrafts}
                >
                  {savingMatrixDrafts ? 'Saving…' : 'Save changes'}
                </button>
              </span>
            </div>
          )}
          <PayrollMatrix
            rows={filteredRows}
            allPositions={rows}
            areaOptions={distinctAreas}
            selectedYear={selectedYear}
            calendarMode={calendarMode}
            headcountDrafts={headcountDrafts}
            onDraftMonthChange={handleDraftMonthChange}
            onPositionClick={(row) => setSelectedRowId(row.node_id)}
            positionDrafts={positionDrafts}
            employeeDrafts={employeeDrafts}
            onDraftPositionField={draftPositionField}
            onDraftEmployeeField={draftEmployeeField}
            onRemoveEmployee={handleRemoveEmployee}
            selectionMode={cloneMode || deleteMode}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
          />
        </>
      )}

      {selectedRow && (
        <section className="payroll-view__editor">
          <h4>Position details</h4>
          <p className="payroll-view__roster-hint" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
            Headcount, "Reports to," and comp are all set directly in the Matrix grid above — this is just the name and area.
          </p>
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
              <AreaAutocomplete
                value={editorValues.area}
                options={distinctAreas}
                onChange={(nextArea) => setEditorValues((prev) => ({ ...prev, area: nextArea }))}
                placeholder="Pick or type an area"
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
        </section>
      )}

      {loading && rows.length === 0 ? <div className="payroll-view__status">Loading payroll...</div> : null}
      {error && rows.length === 0 ? (
        <div className="payroll-view__status payroll-view__status--error">{error}</div>
      ) : null}

      {isModalOpen && (
        <AddPositionModal
          positions={rows}
          areaOptions={distinctAreas}
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
