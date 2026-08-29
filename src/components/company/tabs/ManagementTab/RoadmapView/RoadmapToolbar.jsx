import { useEffect, useState } from 'react'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'

const ZOOM_LEVELS = ['Day', 'Week', 'Month']

function RoadmapToolbar({ zoom, onZoomChange, onAddTask, companies, calendarMode }) {
  const [isAdding, setIsAdding] = useState(false)
  const [formValues, setFormValues] = useState(() => {
    const defaultDate = getDefaultCalendarDate(calendarMode)
    return {
      name: '',
      start: defaultDate,
      end: defaultDate,
      progress: 0,
      dependencies: '',
      responsible: '',
      linkedCompanyId: '',
    }
  })

  const handleFieldChange = (field, value) => {
    setFormValues((prev) => ({ ...prev, [field]: value }))
  }

  useEffect(() => {
    const defaultDate = getDefaultCalendarDate(calendarMode)
    setFormValues((prev) => ({ ...prev, start: defaultDate, end: defaultDate }))
  }, [calendarMode])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!formValues.name.trim()) return

    await onAddTask({
      name: formValues.name.trim(),
      start: formValues.start,
      end: formValues.end,
      progress: Number(formValues.progress) || 0,
      dependencies: formValues.dependencies,
      responsible: formValues.responsible,
      linked_company_id: formValues.linkedCompanyId || null,
    })

    const defaultDate = getDefaultCalendarDate(calendarMode)
    setIsAdding(false)
    setFormValues({
      name: '',
      start: defaultDate,
      end: defaultDate,
      progress: 0,
      dependencies: '',
      responsible: '',
      linkedCompanyId: '',
    })
  }

  return (
    <div className="roadmap-toolbar">
      <div className="roadmap-toolbar__controls">
        {ZOOM_LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            className={
              level === zoom
                ? 'roadmap-toolbar__btn roadmap-toolbar__btn--active'
                : 'roadmap-toolbar__btn'
            }
            onClick={() => onZoomChange(level)}
          >
            {level}
          </button>
        ))}

        <button type="button" className="roadmap-toolbar__btn roadmap-toolbar__btn--strong" onClick={() => setIsAdding((prev) => !prev)}>
          {isAdding ? 'Close add form' : 'Add task'}
        </button>
      </div>

      {isAdding && (
        <form className="roadmap-toolbar__form" onSubmit={handleSubmit}>
          <label className="roadmap-toolbar__field roadmap-toolbar__field--span-2">
            Task name
            <input
              type="text"
              placeholder="Task name"
              value={formValues.name}
              onChange={(event) => handleFieldChange('name', event.target.value)}
            />
          </label>
          <label className="roadmap-toolbar__field">
            Start date
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={formValues.start} onChange={(nextValue) => handleFieldChange('start', nextValue)} />
            ) : (
              <input
                type="date"
                value={formValues.start}
                onChange={(event) => handleFieldChange('start', event.target.value)}
                aria-label="Start date"
              />
            )}
          </label>
          <label className="roadmap-toolbar__field">
            End date
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={formValues.end} onChange={(nextValue) => handleFieldChange('end', nextValue)} />
            ) : (
              <input
                type="date"
                value={formValues.end}
                onChange={(event) => handleFieldChange('end', event.target.value)}
                aria-label="End date"
              />
            )}
          </label>
          <label className="roadmap-toolbar__field">
            Completion (%)
            <input
              type="number"
              min="0"
              max="100"
              value={formValues.progress}
              onChange={(event) => handleFieldChange('progress', event.target.value)}
            />
          </label>
          <label className="roadmap-toolbar__field">
            Dependencies
            <input
              type="text"
              placeholder="Dependencies"
              value={formValues.dependencies}
              onChange={(event) => handleFieldChange('dependencies', event.target.value)}
            />
          </label>
          <label className="roadmap-toolbar__field">
            Responsible
            <input
              type="text"
              placeholder="Responsible"
              value={formValues.responsible}
              onChange={(event) => handleFieldChange('responsible', event.target.value)}
            />
          </label>
          <label className="roadmap-toolbar__field">
            Linked company
            <select
              value={formValues.linkedCompanyId}
              onChange={(event) => handleFieldChange('linkedCompanyId', event.target.value)}
            >
              <option value="">No linked company</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
          <div className="roadmap-toolbar__actions">
            <button type="submit" className="roadmap-toolbar__submit">Save task</button>
          </div>
        </form>
      )}
    </div>
  )
}

export default RoadmapToolbar
