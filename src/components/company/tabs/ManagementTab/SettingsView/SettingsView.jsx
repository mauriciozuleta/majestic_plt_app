import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RoadmapDateInput from '../RoadmapView/RoadmapDateInput'
import { deleteCompany } from '../../../../../services/companies'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { fetchSettings, updateCalendarMode, updateTimeProjection } from '../../../../../services/settings'
import { useAppStore } from '../../../../../store/useAppStore'
import './SettingsView.css'

function SettingsView() {
  const navigate = useNavigate()
  const companies = useAppStore((state) => state.companies)
  const removeCompany = useAppStore((state) => state.removeCompany)
  const [calendarMode, setCalendarMode] = useState('real')
  const [projectionYears, setProjectionYears] = useState(5)
  const [pendingRealStartDate, setPendingRealStartDate] = useState(new Date().toISOString().slice(0, 10))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectedCompanyId, setSelectedCompanyId] = useState('')
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')

  useEffect(() => {
    let cancelled = false

    fetchSettings()
      .then((settings) => {
        if (!cancelled) {
          setCalendarMode(settings.calendar_mode ?? 'real')
          setProjectionYears(Math.max(5, Math.min(10, Number(settings.projection_years ?? 5))))
          setMessage('')
          setMessageType('info')
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setMessage(error.message)
          setMessageType('error')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!companies.length) {
      setSelectedCompanyId('')
      return
    }

    setSelectedCompanyId((currentSelected) => {
      if (companies.some((company) => company.id === currentSelected)) {
        return currentSelected
      }

      return companies[0].id
    })
  }, [companies])

  const selectedCompany = useMemo(
    () => companies.find((company) => company.id === selectedCompanyId) ?? null,
    [companies, selectedCompanyId],
  )

  const handleModeChange = async (nextMode) => {
    if (nextMode === calendarMode) return

    if (!pendingRealStartDate) {
      setMessage('Pick a reference date before changing calendar mode.')
      setMessageType('error')
      return
    }

    const actionLabel = nextMode === 'simulation' ? 'switch to Simulation' : 'switch back to Real'
    const confirmed = window.confirm(
      `Confirm ${actionLabel} mode? This will convert and save all roadmap and payroll dates using ${pendingRealStartDate} as the reference date.`,
    )

    if (!confirmed) return

    setSaving(true)
    setMessage('')
    setMessageType('info')

    try {
      const result = await updateCalendarMode(nextMode, pendingRealStartDate)
      const taskCount = result.tasks_converted ?? 0
      const payrollCount = result.payroll_records_converted ?? 0

      setCalendarMode(result.calendar_mode ?? nextMode)
      setMessage(`Saved. Converted ${taskCount} roadmap tasks and ${payrollCount} payroll start dates.`)
      setMessageType('success')

      companies.forEach((company) => {
        broadcastCompanyDataChange(company.id, 'settings:calendar-mode-changed')
      })
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const handleProjectionYearsChange = async (value) => {
    const nextValue = Number(value)
    if (Number.isNaN(nextValue)) return
    if (nextValue === projectionYears) return

    setSaving(true)
    setMessage('')
    setMessageType('info')

    try {
      const result = await updateTimeProjection(nextValue)
      const nextProjection = Math.max(5, Math.min(10, Number(result.projection_years ?? nextValue)))
      setProjectionYears(nextProjection)
      setMessage(`Saved. Time projection set to ${nextProjection} years.`)
      setMessageType('success')

      companies.forEach((company) => {
        broadcastCompanyDataChange(company.id, 'settings:projection-years-changed')
      })
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="settings-view__status">Loading settings...</div>
  }

  return (
    <section className="settings-view">
      <header className="settings-view__header">
        <h4>Settings</h4>
        <p>Controls here apply to the whole app, not just management.</p>
      </header>

      <div className="settings-view__card">
        <label>
          Calendar mode
          <select value={calendarMode} onChange={(event) => handleModeChange(event.target.value)} disabled={saving}>
            <option value="real">Real</option>
            <option value="simulation">Simulation</option>
          </select>
        </label>

        <label>
          Time projection
          <select
            value={projectionYears}
            onChange={(event) => handleProjectionYearsChange(event.target.value)}
            disabled={saving}
          >
            {Array.from({ length: 6 }, (_, offset) => 5 + offset).map((yearCount) => (
              <option key={yearCount} value={yearCount}>
                {yearCount} years
              </option>
            ))}
          </select>
        </label>

        <label>
          Reference real start date
          <RoadmapDateInput
            value={pendingRealStartDate}
            onChange={setPendingRealStartDate}
            ariaLabel="Reference real start date"
          />
        </label>

        {message ? (
          <div className={`settings-view__message settings-view__message--${messageType}`}>{message}</div>
        ) : null}
      </div>

      <div className="settings-view__card">
        <div className="settings-view__section-heading">
          <h4>Delete company</h4>
          <p>Select a company card, then delete it.</p>
        </div>

        {companies.length === 0 ? (
          <div className="settings-view__status">No companies available.</div>
        ) : (
          <>
            <div className="settings-view__company-grid">
              {companies.map((company) => {
                const isSelected = company.id === selectedCompanyId
                const initials = company.name
                  .split(' ')
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join('')
                  .toUpperCase()

                return (
                  <button
                    key={company.id}
                    type="button"
                    className={`settings-view__company-card ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedCompanyId(company.id)}
                  >
                    <span
                      className="settings-view__company-logo"
                      style={
                        company.logo
                          ? {
                              backgroundImage: `url(${company.logo})`,
                              backgroundSize: 'contain',
                              backgroundPosition: 'center',
                              backgroundRepeat: 'no-repeat',
                              backgroundColor: 'var(--bg-card)',
                            }
                          : {
                              background: `linear-gradient(135deg, ${company.accentFrom}, ${company.accentTo})`,
                            }
                      }
                    >
                      {!company.logo && initials}
                    </span>
                    <span className="settings-view__company-name">{company.name}</span>
                  </button>
                )
              })}
            </div>

            <div className="settings-view__delete-panel">
              {selectedCompany ? (
                <>
                  <div className="settings-view__selected-company">
                    <strong>{selectedCompany.name}</strong>
                    <span>{selectedCompany.companyType}</span>
                  </div>
                  <button
                    type="button"
                    className="settings-view__delete-btn"
                    onClick={async () => {
                      if (!window.confirm(`Delete ${selectedCompany.name}? This removes all related data.`)) return
                      try {
                        await deleteCompany(selectedCompany.id)
                        removeCompany(selectedCompany.id)
                        setSelectedCompanyId('')
                        setMessage(`${selectedCompany.name} was deleted.`)
                        setMessageType('info')
                        navigate('/settings')
                      } catch (error) {
                        setMessage(error.message || 'Failed to delete company. It has not been removed — please try again.')
                        setMessageType('error')
                      }
                    }}
                  >
                    Delete selected company
                  </button>
                </>
              ) : (
                <div className="settings-view__status">Select a company to delete.</div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  )
}

export default SettingsView