import { useEffect, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { formatCalendarDateCompact } from '../../../../../services/calendarDates'

function TaskEditPanel({ task, onSave, onDelete, onIndent, onOutdent, onMoveUp, onMoveDown, childrenTasks = [], companies, calendarMode }) {
  const [formValues, setFormValues] = useState(task)
  const isGroupTask = childrenTasks.length > 0

  useEffect(() => {
    setFormValues(task)
  }, [task])

  const handleFieldChange = (field, value) => {
    setFormValues((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    await onSave({
      name: formValues.name,
      start: formValues.start,
      end: formValues.end,
      progress: Number(formValues.progress) || 0,
      dependencies: formValues.dependencies ?? '',
      responsible: formValues.responsible ?? '',
      parent_task_id: formValues.parent_task_id || null,
      linked_company_id: formValues.linked_company_id || null,
    })
  }

  return (
    <section className="roadmap-edit-panel">
      <h4>Edit task</h4>
      <div className="roadmap-edit-panel__hierarchy-actions">
        <button type="button" onClick={onMoveUp} disabled={!onMoveUp} title="Move task up">
          ↑ Move up
        </button>
        <button type="button" onClick={onMoveDown} disabled={!onMoveDown} title="Move task down">
          ↓ Move down
        </button>
        <button type="button" onClick={onIndent} disabled={!onIndent} title="Indent under previous task">
          ← Indent
        </button>
        <button type="button" onClick={onOutdent} disabled={!onOutdent} title="Un-indent to parent level">
          → Un-indent
        </button>
      </div>
      <form className="roadmap-edit-panel__form" onSubmit={handleSubmit}>
        <label>
          Task name
          <input
            type="text"
            value={formValues.name}
            onChange={(event) => handleFieldChange('name', event.target.value)}
          />
        </label>
        <label>
          Start date
          {calendarMode === 'simulation' && !isGroupTask ? (
            <SimulationDatePicker value={formValues.start} onChange={(nextValue) => handleFieldChange('start', nextValue)} />
          ) : (
            <input
              type={calendarMode === 'simulation' ? 'text' : 'date'}
              value={calendarMode === 'simulation' ? formatCalendarDateCompact(formValues.start, calendarMode) : formValues.start}
              onChange={(event) => handleFieldChange('start', event.target.value)}
              aria-label="Start date"
              readOnly={isGroupTask && calendarMode === 'simulation'}
              disabled={isGroupTask}
            />
          )}
        </label>
        <label>
          End date
          {calendarMode === 'simulation' && !isGroupTask ? (
            <SimulationDatePicker value={formValues.end} onChange={(nextValue) => handleFieldChange('end', nextValue)} />
          ) : (
            <input
              type={calendarMode === 'simulation' ? 'text' : 'date'}
              value={calendarMode === 'simulation' ? formatCalendarDateCompact(formValues.end, calendarMode) : formValues.end}
              onChange={(event) => handleFieldChange('end', event.target.value)}
              aria-label="End date"
              readOnly={isGroupTask && calendarMode === 'simulation'}
              disabled={isGroupTask}
            />
          )}
        </label>
        <label>
          Progress (%)
          <input
            type="number"
            min="0"
            max="100"
            value={formValues.progress}
            onChange={(event) => handleFieldChange('progress', event.target.value)}
            disabled={isGroupTask}
          />
        </label>
        <label>
          Responsible
          <input
            type="text"
            value={formValues.responsible ?? ''}
            onChange={(event) => handleFieldChange('responsible', event.target.value)}
          />
        </label>
        <label>
          Dependencies
          <input
            type="text"
            value={formValues.dependencies ?? ''}
            onChange={(event) => handleFieldChange('dependencies', event.target.value)}
          />
        </label>
        <label>
          Linked company
          <select
            value={formValues.linked_company_id ?? ''}
            onChange={(event) => handleFieldChange('linked_company_id', event.target.value)}
          >
            <option value="">No linked company</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </select>
        </label>

        <div className="roadmap-edit-panel__actions">
          <button type="submit" className="roadmap-edit-panel__save">Save</button>
          <button type="button" className="roadmap-edit-panel__delete" onClick={onDelete}>Delete</button>
        </div>
      </form>

      {isGroupTask ? (
        <div className="roadmap-edit-panel__children">
          <h5>Children tasks</h5>
          <div className="roadmap-edit-panel__children-grid roadmap-edit-panel__children-grid--head">
            <span>Task</span>
            <span>Start</span>
            <span>Finish</span>
            <span>Progress</span>
            <span>Responsible</span>
          </div>
          {childrenTasks.map((child) => (
            <div key={child.id} className="roadmap-edit-panel__children-grid">
              <span>{child.name}</span>
              <span>{formatCalendarDateCompact(child.start, calendarMode)}</span>
              <span>{formatCalendarDateCompact(child.end, calendarMode)}</span>
              <span>{child.progress}%</span>
              <span>{child.responsible || '—'}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default TaskEditPanel
