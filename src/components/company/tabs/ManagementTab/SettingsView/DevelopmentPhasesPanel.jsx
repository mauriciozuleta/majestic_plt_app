import { useEffect, useState } from 'react'
import RoadmapDateInput from '../RoadmapView/RoadmapDateInput'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { formatCalendarDateCompact } from '../../../../../services/calendarDates'
import { fetchSettings, updateDevelopmentPhases } from '../../../../../services/settings'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { useAppStore } from '../../../../../store/useAppStore'

const MIN_PHASES = 1
const MAX_PHASES = 20

// An alternative to the single portfolio-wide "Reference real start date"
// above: each company (see its Phase selector in the Add/Edit company form)
// anchors its own Year 1 / Month 1 / Day 1 to whichever phase it's assigned,
// instead of every company sharing one date. Every phase needs its own
// start date before this can be saved as enabled — a phase with no date
// would leave any company assigned to it with no anchor at all.
// The input itself follows the same convention as every other date field in
// this app (e.g. Roadmap task dates): in Simulation mode it's the Year 1-20
// / Month 1-12 / Day 1-30 dropdown picker; in Real mode it's a plain
// calendar, same as "Reference real start date" right above it.
function DevelopmentPhasesPanel({ calendarMode }) {
  const companies = useAppStore((state) => state.companies)
  const [loading, setLoading] = useState(true)
  const [enabled, setEnabled] = useState(false)
  const [count, setCount] = useState(1)
  const [startDatesByPhase, setStartDatesByPhase] = useState({})
  const [selectedPhase, setSelectedPhase] = useState(1)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setEnabled(Boolean(settings.phases_enabled))
        setCount(settings.phases_count || 1)
        const byPhase = {}
        ;(settings.phases || []).forEach((phase) => {
          byPhase[phase.phase_number] = phase.start_date
        })
        setStartDatesByPhase(byPhase)
      })
      .catch((error) => setMessage(error.message))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const phaseNumbers = Array.from({ length: Math.max(1, count) }, (_, index) => index + 1)
  const allPhasesHaveDates = !enabled || phaseNumbers.every((number) => Boolean(startDatesByPhase[number]))
  const canSave = allPhasesHaveDates && !saving

  const handleCountChange = (value) => {
    const nextCount = Math.max(MIN_PHASES, Math.min(MAX_PHASES, Number(value) || MIN_PHASES))
    setCount(nextCount)
    if (selectedPhase > nextCount) setSelectedPhase(nextCount)
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const phases = enabled ? phaseNumbers.map((number) => ({ phase_number: number, start_date: startDatesByPhase[number] })) : []
      await updateDevelopmentPhases({ enabled, count: enabled ? count : undefined, phases })
      setMessage('Saved.')
      setMessageType('success')
      companies.forEach((company) => broadcastCompanyDataChange(company.id, 'settings:development-phases-changed'))
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="settings-view__card">
        <div className="settings-view__section-heading">
          <h4>Development phases</h4>
        </div>
        <div className="settings-view__status">Loading...</div>
      </div>
    )
  }

  return (
    <div className="settings-view__card">
      <div className="settings-view__section-heading">
        <h4>Development phases</h4>
        <p>
          Anchor each company's Year 1 / Month 1 / Day 1 to a phase's own start date instead of one shared reference
          date — useful when different companies begin operating at different times.
        </p>
      </div>

      <label className="settings-view__phases-toggle">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        Set up development phases
      </label>

      {enabled && (
        <>
          <label>
            Number of Projected Phases
            <input
              type="number"
              min={MIN_PHASES}
              max={MAX_PHASES}
              value={count}
              onChange={(event) => handleCountChange(event.target.value)}
            />
          </label>

          <div className="settings-view__phase-date-row">
            <label>
              Select Phase
              <select value={selectedPhase} onChange={(event) => setSelectedPhase(Number(event.target.value))}>
                {phaseNumbers.map((number) => (
                  <option key={number} value={number}>
                    Phase {number}
                    {startDatesByPhase[number] ? '' : ' — no start date yet'}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Phase Start Date
              {calendarMode === 'simulation' ? (
                <SimulationDatePicker
                  value={startDatesByPhase[selectedPhase] || ''}
                  onChange={(value) => setStartDatesByPhase((prev) => ({ ...prev, [selectedPhase]: value }))}
                />
              ) : (
                <RoadmapDateInput
                  value={startDatesByPhase[selectedPhase] || ''}
                  onChange={(value) => setStartDatesByPhase((prev) => ({ ...prev, [selectedPhase]: value }))}
                  ariaLabel={`Phase ${selectedPhase} start date`}
                />
              )}
            </label>
          </div>

          <ul className="settings-view__phase-list">
            {phaseNumbers.map((number) => (
              <li key={number}>
                Phase {number}:{' '}
                {startDatesByPhase[number] ? formatCalendarDateCompact(startDatesByPhase[number], calendarMode) : <em>not set</em>}
              </li>
            ))}
          </ul>

          {!allPhasesHaveDates && (
            <div className="settings-view__status-hint">Every phase needs a start date before you can save.</div>
          )}
        </>
      )}

      <button type="button" className="settings-view__btn" onClick={handleSave} disabled={!canSave}>
        {saving ? 'Saving…' : 'Save'}
      </button>

      {message ? <div className={`settings-view__message settings-view__message--${messageType}`}>{message}</div> : null}
    </div>
  )
}

export default DevelopmentPhasesPanel
