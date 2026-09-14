import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAuditSettings, runAuditNow, updateAuditSettings } from '../../../../../services/accountingAudit'
import { useAppStore } from '../../../../../store/useAppStore'

const INTERVAL_OPTIONS = [
  { value: 1, label: 'Daily' },
  { value: 7, label: 'Weekly' },
  { value: 14, label: 'Every 2 weeks' },
  { value: 30, label: 'Monthly' },
]

function formatLastRun(isoString) {
  if (!isoString) return 'Never run yet'
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime())) return isoString
  return parsed.toLocaleString()
}

// The auditor traces every Commercial Operations entry through its bank
// transaction and journal postings independently of the app's own posting
// engine (see backend/accounting_auditor.py) — this card is just the on/off
// switch and schedule, not where results are read. Portfolio-wide (not
// per-country), so it's its own top-level card rather than one of the
// per-country tax pills below.
function AccountingHealthCheckCard() {
  const companies = useAppStore((state) => state.companies)
  const [settings, setSettings] = useState(null)
  const [status, setStatus] = useState('loading')
  const [saving, setSaving] = useState(false)
  const [runningNow, setRunningNow] = useState(false)
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')

  useEffect(() => {
    let cancelled = false
    fetchAuditSettings()
      .then((data) => {
        if (cancelled) return
        setSettings(data)
        setStatus('ready')
      })
      .catch((error) => {
        if (cancelled) return
        setMessage(error.message)
        setMessageType('error')
        setStatus('ready')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleToggleEnabled = async () => {
    if (!settings) return
    const nextEnabled = !settings.enabled
    setSaving(true)
    setMessage('')
    try {
      const updated = await updateAuditSettings({ enabled: nextEnabled })
      setSettings(updated)
      setMessage(nextEnabled ? 'Accounting Health Check enabled.' : 'Accounting Health Check disabled.')
      setMessageType('success')
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const handleIntervalChange = async (event) => {
    const intervalDays = Number(event.target.value)
    setSaving(true)
    setMessage('')
    try {
      const updated = await updateAuditSettings({ interval_days: intervalDays })
      setSettings(updated)
      setMessage('Saved.')
      setMessageType('success')
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const handleScopeChange = async (event) => {
    const scopeCompanyId = event.target.value || null
    setSaving(true)
    setMessage('')
    try {
      const updated = await updateAuditSettings({ scope_company_id: scopeCompanyId })
      setSettings(updated)
      setMessage('Saved.')
      setMessageType('success')
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const handleRunNow = async () => {
    setRunningNow(true)
    setMessage('')
    try {
      const run = await runAuditNow(settings?.scope_company_id)
      setSettings((prev) => (prev ? { ...prev, last_run_at: run.finished_at } : prev))
      setMessage(`Run complete: ${run.entries_checked} entries checked, ${run.findings_count} finding(s).`)
      setMessageType(run.findings_count > 0 ? 'error' : 'success')
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setRunningNow(false)
    }
  }

  if (status === 'loading' || !settings) {
    return (
      <div className="settings-view__card">
        <div className="settings-view__section-heading">
          <h4>Accounting Health Check</h4>
        </div>
        <div className="settings-view__status">Loading...</div>
      </div>
    )
  }

  return (
    <div className="settings-view__card">
      <div className="settings-view__section-heading">
        <h4>Accounting Health Check</h4>
        <p>
          Independently traces every commercial-operations entry through its bank transaction and journal
          postings, catching discrepancies the posting engine itself wouldn't notice.
        </p>
      </div>

      <label className="settings-view__audit-toggle-row">
        <input type="checkbox" checked={settings.enabled} onChange={handleToggleEnabled} disabled={saving} />
        Run automatically
      </label>

      <label>
        How often
        <select value={settings.interval_days} onChange={handleIntervalChange} disabled={saving || !settings.enabled}>
          {INTERVAL_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        Scope
        <select value={settings.scope_company_id ?? ''} onChange={handleScopeChange} disabled={saving}>
          <option value="">All companies</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </select>
      </label>

      <div className="settings-view__audit-status-row">
        <span className="settings-view__status-hint">Last run: {formatLastRun(settings.last_run_at)}</span>
      </div>

      <div className="settings-view__audit-actions-row">
        <button type="button" className="settings-view__btn" onClick={handleRunNow} disabled={runningNow}>
          {runningNow ? 'Running…' : 'Run now'}
        </button>
        <Link to="/accounting-audit" className="settings-view__btn">
          View results
        </Link>
      </div>

      {message ? <div className={`settings-view__message settings-view__message--${messageType}`}>{message}</div> : null}
    </div>
  )
}

export default AccountingHealthCheckCard
