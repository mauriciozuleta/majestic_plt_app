import { Fragment, useCallback, useEffect, useState } from 'react'
import {
  approveHeldUpdate,
  fetchDataHistoryDatasets,
  fetchDataHistoryDiff,
  fetchDataHistoryLog,
  fetchHeldUpdates,
  pinDataVersion,
  rejectHeldUpdate,
  restoreDataVersion,
} from '../../../../../services/dataHistory'
import './DataHistoryCard.css'

const formatWhen = (iso) => {
  const date = iso ? new Date(iso) : null
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : '—'
}
const formatSize = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((bytes || 0) / 1024))} KB`)
const number = (value) => (value == null ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 }))

// A readable one-line summary of what changed (products, market size or file).
function describeChange(change) {
  if (!change) return ''
  if (change.type === 'products') {
    const parts = [`${number(change.old_count)} → ${number(change.new_count)} products`]
    if (change.added) parts.push(`${number(change.added)} added`)
    if (change.removed) parts.push(`${number(change.removed)} removed`)
    if (change.price_changed) parts.push(`${number(change.price_changed)} prices changed`)
    return parts.join(' · ')
  }
  if (change.type === 'market_size') {
    const pct = change.change_pct == null ? '' : ` (${change.change_pct > 0 ? '+' : ''}${change.change_pct}%)`
    return `total ${number(change.old_total)} → ${number(change.new_total)}${pct} · ${number(change.old_rows)} → ${number(change.new_rows)} rows`
  }
  if (change.identical) return 'identical'
  const lines = change.lines_added != null ? ` · +${number(change.lines_added)} / −${number(change.lines_removed)} lines` : ''
  return `${formatSize(change.old_size)} → ${formatSize(change.new_size)}${lines}`
}

// Settings ▸ Data history: refreshes that looked worse than what is stored wait here for a decision, and every stored dataset keeps its versions
// (restore any of them). Backend: backend/data_history/.
function DataHistoryCard() {
  const [datasets, setDatasets] = useState([])
  const [held, setHeld] = useState([])
  const [status, setStatus] = useState('loading')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(null)
  const [openScope, setOpenScope] = useState(null)
  const [log, setLog] = useState([])
  const [changes, setChanges] = useState({})

  const load = useCallback(async () => {
    try {
      const [sets, pending] = await Promise.all([fetchDataHistoryDatasets(), fetchHeldUpdates()])
      setDatasets(sets)
      setHeld(pending)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const act = async (key, action, done) => {
    setBusy(key)
    setMessage('')
    try {
      await action()
      setMessage(done)
      await load()
      if (openScope) setLog(await fetchDataHistoryLog(openScope))
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(null)
    }
  }

  const toggle = async (scope) => {
    if (openScope === scope) {
      setOpenScope(null)
      return
    }
    setOpenScope(scope)
    setLog([])
    try {
      const versions = await fetchDataHistoryLog(scope)
      setLog(versions)
      // what each of the latest versions changed against the one before it
      const recent = versions.slice(0, 8)
      const entries = await Promise.all(
        recent.map((item, index) => (versions[index + 1] ? fetchDataHistoryDiff(scope, item.version, versions[index + 1].version).catch(() => null) : null)),
      )
      setChanges(Object.fromEntries(recent.map((item, index) => [`${scope}#${item.version}`, entries[index]])))
    } catch (error) {
      setMessage(error.message)
    }
  }

  return (
    <div className="settings-view__card data-history">
      <div className="settings-view__section-heading">
        <h4>Data history</h4>
        <p>
          Every refresh keeps the version before it, so any dataset can be put back. A refresh that comes back empty or much smaller than what is stored is
          not saved: it waits here for you.
        </p>
      </div>

      {status === 'loading' && <p className="data-history__hint">Loading…</p>}
      {message && (
        <p className="data-history__note" role="status">
          {message}
        </p>
      )}

      {held.length > 0 && (
        <div className="data-history__held" data-testid="held-updates">
          <h5>Waiting for your approval ({held.length})</h5>
          {held.map((item) => (
            <div key={item.id} className="data-history__held-item">
              <strong>{item.label}</strong>
              <span className="data-history__hint">
                {formatWhen(item.created_at)} · {item.actor}
              </span>
              <ul>
                {item.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
              <p className="data-history__hint">If approved: {describeChange(item.compare)}. The stored data stays as it is until you decide.</p>
              <div className="data-history__actions">
                <button
                  type="button"
                  className="settings-view__btn"
                  disabled={busy != null}
                  onClick={() => act(`a${item.id}`, () => approveHeldUpdate(item.id), 'Update approved and saved.')}
                >
                  {busy === `a${item.id}` ? 'Saving…' : 'Approve and save'}
                </button>
                <button
                  type="button"
                  className="settings-view__btn"
                  disabled={busy != null}
                  onClick={() => act(`r${item.id}`, () => rejectHeldUpdate(item.id), 'Update rejected; the stored data is unchanged.')}
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {status === 'ready' && datasets.length === 0 && <p className="data-history__hint">No history yet — it starts with today&apos;s baseline when the backend starts.</p>}

      {datasets.length > 0 && (
        <table className="data-history__table">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Versions</th>
              <th>Latest</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset) => (
              <Fragment key={dataset.scope}>
                <tr className={openScope === dataset.scope ? 'is-open' : ''}>
                  <td>
                    {dataset.label}
                    {dataset.held > 0 && <span className="data-history__badge"> held</span>}
                  </td>
                  <td>{dataset.versions}</td>
                  <td>
                    v{dataset.version} · {formatWhen(dataset.created_at)}
                    <div className="data-history__hint">
                      {dataset.actor} — {dataset.reason}
                    </div>
                  </td>
                  <td>{formatSize(dataset.raw_size)}</td>
                  <td>
                    <button type="button" className="settings-view__btn" onClick={() => toggle(dataset.scope)} aria-expanded={openScope === dataset.scope}>
                      {openScope === dataset.scope ? 'Hide' : 'Versions'}
                    </button>
                  </td>
                </tr>
                {openScope === dataset.scope && (
                  <tr className="data-history__versions">
                    <td colSpan={5}>
                      {log.length === 0 && <span className="data-history__hint">Loading…</span>}
                      {log.map((item, index) => (
                        <div key={item.version} className="data-history__version">
                          <span>
                            <strong>v{item.version}</strong> · {formatWhen(item.created_at)} · {item.actor} — {item.reason}
                            {item.kind === 'deleted' && <em> (deleted)</em>}
                            {item.pinned && <em> (pinned)</em>}
                            <span className="data-history__hint"> {describeChange(changes[`${dataset.scope}#${item.version}`])}</span>
                          </span>
                          <span className="data-history__actions">
                            {index > 0 && item.kind !== 'deleted' && (
                              <button
                                type="button"
                                className="settings-view__btn"
                                disabled={busy != null}
                                onClick={() =>
                                  window.confirm(`Restore version ${item.version} of "${dataset.label}"? It becomes a new version; nothing is lost.`) &&
                                  act(`s${dataset.scope}${item.version}`, () => restoreDataVersion(dataset.scope, item.version), `Version ${item.version} restored.`)
                                }
                              >
                                Restore
                              </button>
                            )}
                            <button
                              type="button"
                              className="settings-view__btn"
                              disabled={busy != null}
                              onClick={() => act(`p${dataset.scope}${item.version}`, () => pinDataVersion(dataset.scope, item.version, !item.pinned), item.pinned ? 'Pin removed.' : 'Version pinned.')}
                            >
                              {item.pinned ? 'Unpin' : 'Pin'}
                            </button>
                          </span>
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default DataHistoryCard
