import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAuditRun, fetchAuditRuns, runAuditNow } from '../../services/accountingAudit'
import { useAppStore } from '../../store/useAppStore'
import './AccountingAuditView.css'

function formatTimestamp(isoString) {
  if (!isoString) return '—'
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime())) return isoString
  return parsed.toLocaleString()
}

function AccountingAuditView() {
  const companies = useAppStore((state) => state.companies)
  const companyNameById = useMemo(() => new Map(companies.map((company) => [company.id, company.name])), [companies])

  const [runs, setRuns] = useState([])
  const [runsStatus, setRunsStatus] = useState('loading')
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetailStatus, setRunDetailStatus] = useState('idle')
  const [runningNow, setRunningNow] = useState(false)
  const [error, setError] = useState('')
  const [severityFilter, setSeverityFilter] = useState('all')

  const loadRuns = () => {
    setRunsStatus('loading')
    fetchAuditRuns()
      .then((data) => {
        setRuns(data)
        setRunsStatus('ready')
        if (data.length > 0) {
          setSelectedRunId((current) => current ?? data[0].id)
        }
      })
      .catch((err) => {
        setError(err.message)
        setRunsStatus('ready')
      })
  }

  useEffect(loadRuns, [])

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null)
      return
    }
    let cancelled = false
    setRunDetailStatus('loading')
    fetchAuditRun(selectedRunId)
      .then((data) => {
        if (cancelled) return
        setSelectedRun(data)
        setRunDetailStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setRunDetailStatus('ready')
      })
    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  const handleRunNow = async () => {
    setRunningNow(true)
    setError('')
    try {
      const run = await runAuditNow(null)
      setSelectedRunId(run.id)
      loadRuns()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunningNow(false)
    }
  }

  const findings = selectedRun?.findings ?? []
  const visibleFindings = severityFilter === 'all' ? findings : findings.filter((finding) => finding.severity === severityFilter)
  const errorCount = findings.filter((finding) => finding.severity === 'error').length
  const warningCount = findings.filter((finding) => finding.severity === 'warning').length

  return (
    <div className="accounting-audit-view">
      <header className="accounting-audit-view__header">
        <div>
          <h3>Accounting Health Check</h3>
          <p>Independent audit history — traces every commercial-operations entry through its bank transaction and journal postings.</p>
        </div>
        <div className="accounting-audit-view__header-actions">
          <button type="button" className="accounting-audit-view__btn" onClick={handleRunNow} disabled={runningNow}>
            {runningNow ? 'Running…' : 'Run now'}
          </button>
          <Link to="/settings" className="accounting-audit-view__btn accounting-audit-view__btn--ghost">
            Back to Settings
          </Link>
        </div>
      </header>

      {error ? <div className="accounting-audit-view__status accounting-audit-view__status--error">{error}</div> : null}

      <div className="accounting-audit-view__layout">
        <aside className="accounting-audit-view__runs">
          <h4>Run history</h4>
          {runsStatus === 'loading' ? (
            <div className="accounting-audit-view__status">Loading…</div>
          ) : runs.length === 0 ? (
            <div className="accounting-audit-view__status">No audit runs yet. Click "Run now" to check the books.</div>
          ) : (
            <ul className="accounting-audit-view__run-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    className={`accounting-audit-view__run-item ${run.id === selectedRunId ? 'is-selected' : ''}`}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <span className={`accounting-audit-view__run-badge accounting-audit-view__run-badge--${run.status}`}>
                      {run.status}
                    </span>
                    <span className="accounting-audit-view__run-item-meta">
                      <span>{formatTimestamp(run.started_at)}</span>
                      <span>
                        {run.scope_company_id ? companyNameById.get(run.scope_company_id) ?? run.scope_company_id : 'All companies'} ·{' '}
                        {run.triggered_by}
                      </span>
                      <span className={run.findings_count > 0 ? 'has-findings' : 'no-findings'}>
                        {run.findings_count} finding(s) in {run.entries_checked} entries
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="accounting-audit-view__detail">
          {runDetailStatus === 'loading' ? (
            <div className="accounting-audit-view__status">Loading run…</div>
          ) : !selectedRun ? (
            <div className="accounting-audit-view__status">Select a run to see its findings.</div>
          ) : (
            <>
              <div className="accounting-audit-view__summary">
                <div className="accounting-audit-view__summary-metric">
                  <span className="label">Entries checked</span>
                  <span className="value">{selectedRun.entries_checked}</span>
                </div>
                <div className="accounting-audit-view__summary-metric is-error">
                  <span className="label">Errors</span>
                  <span className="value">{errorCount}</span>
                </div>
                <div className="accounting-audit-view__summary-metric is-warning">
                  <span className="label">Warnings</span>
                  <span className="value">{warningCount}</span>
                </div>
                <div className="accounting-audit-view__summary-metric">
                  <span className="label">Finished</span>
                  <span className="value">{formatTimestamp(selectedRun.finished_at)}</span>
                </div>
              </div>

              {selectedRun.error_message ? (
                <div className="accounting-audit-view__status accounting-audit-view__status--error">
                  Run failed: {selectedRun.error_message}
                </div>
              ) : null}

              {findings.length === 0 ? (
                <div className="accounting-audit-view__status accounting-audit-view__status--clean">
                  No discrepancies found — the books trace cleanly.
                </div>
              ) : (
                <>
                  <div className="accounting-audit-view__filter-row">
                    <label>
                      Severity
                      <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}>
                        <option value="all">All ({findings.length})</option>
                        <option value="error">Errors ({errorCount})</option>
                        <option value="warning">Warnings ({warningCount})</option>
                      </select>
                    </label>
                  </div>
                  <div className="accounting-audit-view__table-scroll">
                    <table className="accounting-audit-view__table">
                      <thead>
                        <tr>
                          <th>Severity</th>
                          <th>Company</th>
                          <th>Entry</th>
                          <th>Code</th>
                          <th>Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleFindings.map((finding) => (
                          <tr key={finding.id}>
                            <td>
                              <span className={`accounting-audit-view__severity-pill accounting-audit-view__severity-pill--${finding.severity}`}>
                                {finding.severity}
                              </span>
                            </td>
                            <td>{companyNameById.get(finding.company_id) ?? finding.company_id}</td>
                            <td className="accounting-audit-view__entry-cell">
                              {finding.entry_id ? finding.entry_id : <em>Company-level</em>}
                            </td>
                            <td className="accounting-audit-view__code-cell">{finding.code}</td>
                            <td>{finding.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}

export default AccountingAuditView
