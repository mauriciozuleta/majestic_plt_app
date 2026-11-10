import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchHsQueue, saveHsCodes, suggestHsCodes, validateHsCodes } from '../../services/hsCodes'
import { fetchLocalModels } from '../../services/localModels'
import HsCodeCell from '../hsCodes/HsCodeCell'
import './MissingDataModal.css'

const MODEL_BATCH = 12 // the backend asks a model for at most this many products per call
const REASON = { no_code: 'No HS code', heading_only: 'Heading only', warning: 'Check', unreviewed: 'AI-suggested' }
const money = (value) => (value == null ? '' : Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 }))

function StatusPill({ validation, checking }) {
  if (checking) return <span className="missing-data__status is-checking">checking…</span>
  if (!validation) return null
  const label = validation.status === 'ok' ? 'valid' : validation.status === 'warning' ? 'check' : 'invalid'
  return (
    <span className={`missing-data__status is-${validation.status}`} title={validation.messages.join(' ')}>
      {label}
    </span>
  )
}

// The form behind the red "need HS" pill of Market Analysis ▸ Country Product Portfolio: the products of the country that have no HS code yet, only a 4-digit heading,
// a warning, or a code nobody has looked at. Type the code (a 4-digit heading is padded with zeros), or press a Suggest button: the free one uses curated rules and the same
// product in other countries; a local model and Claude (credits) run only when pressed. Every code is checked against Comtrade's HS reference before it can be saved.
function HsCodesModal({ country, onClose, onSaved }) {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loadState, setLoadState] = useState('loading')
  const [filter, setFilter] = useState('')
  const [checking, setChecking] = useState({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [suggesting, setSuggesting] = useState('')
  const [localModels, setLocalModels] = useState([])
  const [localModel, setLocalModel] = useState('')
  const timers = useRef({})

  useEffect(() => {
    let cancelled = false
    fetchHsQueue(country)
      .then((data) => {
        if (cancelled) return
        setTotal(data.total)
        setRows(data.items.map((item) => ({ ...item, key: item.name.toLowerCase(), code: '', origin: null, note: '', validation: null })))
        setLoadState('ready')
      })
      .catch((error) => !cancelled && setLoadState(error.message || 'error'))
    fetchLocalModels()
      .then((data) => !cancelled && setLocalModels((data.models || []).map((model) => model.name)))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [country])

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const patchRow = useCallback((key, patch) => setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...patch } : row))), [])

  const validateLater = useCallback(
    (row, code) => {
      clearTimeout(timers.current[row.key])
      if (!code.trim()) {
        patchRow(row.key, { validation: null })
        return
      }
      setChecking((previous) => ({ ...previous, [row.key]: true }))
      timers.current[row.key] = setTimeout(() => {
        validateHsCodes([{ country, name: row.name, category: row.category, code }])
          .then(([validation]) => patchRow(row.key, { validation }))
          .catch(() => patchRow(row.key, { validation: { status: 'warning', messages: ['The code could not be checked.'] } }))
          .finally(() => setChecking((previous) => ({ ...previous, [row.key]: false })))
      }, 500)
    },
    [country, patchRow],
  )

  const edit = (row, code) => {
    patchRow(row.key, { code, origin: 'manual', note: '' })
    validateLater(row, code)
  }

  const blanks = rows.filter((row) => !row.code.trim())

  // runs one suggestion call per batch and puts what comes back into the empty rows; nothing is saved
  const suggest = async (kind) => {
    const targets = blanks
    if (!targets.length || suggesting) return
    setMessage('')
    setSuggesting(kind)
    const options = kind === 'free' ? {} : kind === 'local' ? { allowLocal: true, localModel } : { allowAi: true }
    const batchSize = kind === 'free' ? targets.length : MODEL_BATCH
    const problems = []
    let found = 0
    try {
      for (let start = 0; start < targets.length; start += batchSize) {
        const batch = targets.slice(start, start + batchSize)
        // eslint-disable-next-line no-await-in-loop -- one model call at a time
        const { results, errors } = await suggestHsCodes(batch.map((row) => ({ country, name: row.name, category: row.category })), options)
        problems.push(...errors)
        results.forEach((result, index) => {
          const row = batch[index]
          if (!result.suggestion) return
          found += 1
          patchRow(row.key, { code: result.suggestion.code, origin: result.suggestion.method, note: result.suggestion.note, validation: result.validation })
        })
      }
      setMessage(`${found} suggestion${found === 1 ? '' : 's'} found.${problems.length ? ` ${problems[0]}` : ''} Nothing is saved until you press Save to DB.`)
    } catch (error) {
      setMessage(`Suggest failed: ${error.message}`)
    } finally {
      setSuggesting('')
    }
  }

  const filled = rows.filter((row) => row.code.trim())
  const saveable = filled.filter((row) => row.validation && row.validation.status !== 'error' && !checking[row.key])
  const invalid = filled.filter((row) => row.validation?.status === 'error')

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const result = await saveHsCodes(
        saveable.map((row) => ({ country, name: row.name, category: row.category, code: row.code, method: row.origin === 'manual' ? 'manual' : row.origin, note: row.origin === 'manual' ? null : row.note })),
        'user',
      )
      const refusedNames = new Set(result.refused.map((item) => item.name))
      const savedKeys = new Set(saveable.filter((row) => !refusedNames.has(row.name)).map((row) => row.key))
      setRows((previous) => previous.filter((row) => !savedKeys.has(row.key)))
      setMessage(`${result.saved} saved. ${result.refused.length ? `${result.refused.length} refused. ` : ''}The tables and pills are updated.`)
      onSaved?.()
    } catch (error) {
      setMessage(`Could not save: ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  const shown = useMemo(() => rows.filter((row) => !filter.trim() || row.name.toLowerCase().includes(filter.trim().toLowerCase())), [rows, filter])

  return (
    <div className="missing-data__overlay" role="dialog" aria-modal="true" aria-label={`HS codes for ${country}`} onClick={onClose}>
      <div className="missing-data" onClick={(event) => event.stopPropagation()}>
        <header className="missing-data__header">
          <div>
            <h3>HS codes — {country}</h3>
            <p>
              A product without an HS code cannot be traded. A code is <strong>{'<country initials><6-digit HS code>'}</strong>, for example JM070200. Type the HS code (a 4-digit heading is
              padded with zeros), or press Suggest. Every code is checked against the Comtrade HS list before it can be saved. Showing the {rows.length} most urgent of {total}.
            </p>
          </div>
          <button type="button" className="missing-data__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="missing-data__toolbar">
          <input type="search" placeholder="Filter products" value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter products" />
          <span className="missing-data__count">
            {filled.length} of {rows.length} filled
          </span>
          <button type="button" className="missing-data__ai" onClick={() => suggest('free')} disabled={!!suggesting || !blanks.length} title="Free: curated rules and the same product coded in another country. Nothing is saved until you press Save to DB.">
            {suggesting === 'free' ? 'Suggesting…' : `Suggest (free) (${blanks.length})`}
          </button>
          {localModels.length > 0 && (
            <>
              <select value={localModel} onChange={(event) => setLocalModel(event.target.value)} aria-label="Local model">
                <option value="">Local model…</option>
                {localModels.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button type="button" className="missing-data__ai" onClick={() => suggest('local')} disabled={!!suggesting || !blanks.length || !localModel} title="Free but slow and less accurate: a model on this computer chooses from the HS list. Check what it suggests.">
                {suggesting === 'local' ? 'Local model working…' : 'Suggest (local)'}
              </button>
            </>
          )}
          <button type="button" className="missing-data__ai" onClick={() => suggest('ai')} disabled={!!suggesting || !blanks.length} title="Uses Claude and spends credits. Nothing is saved until you press Save to DB.">
            {suggesting === 'ai' ? 'AI searching…' : 'AI Search (credits)'}
          </button>
        </div>

        <div className="missing-data__body">
          {loadState === 'loading' && <p className="missing-data__hint">Loading…</p>}
          {loadState !== 'loading' && loadState !== 'ready' && <p className="missing-data__error">{loadState}</p>}
          {loadState === 'ready' && rows.length === 0 && <p className="missing-data__hint">Every product of {country} has a confirmed HS code.</p>}
          {loadState === 'ready' && rows.length > 0 && (
            <table className="missing-data__table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Sold as</th>
                  <th>Now</th>
                  <th>HS code (4 or 6 digits)</th>
                  <th>Check</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <div className="missing-data__name">{row.name}</div>
                      <div className="missing-data__sub">
                        {row.category || '—'}
                        {row.in_comparison ? ' · in a saved comparison' : ''}
                      </div>
                    </td>
                    <td>
                      <div className="missing-data__sub">
                        {row.example?.unit || '—'} · {money(row.example?.price)}
                      </div>
                    </td>
                    <td>
                      <HsCodeCell hs={row.hs} />
                      <div className="missing-data__sub">{REASON[row.reason]}</div>
                    </td>
                    <td>
                      <input type="text" inputMode="numeric" maxLength={12} placeholder="e.g. 0702 or 070200" value={row.code} onChange={(event) => edit(row, event.target.value)} aria-label={`HS code of ${row.name}`} />
                    </td>
                    <td>
                      <StatusPill validation={row.validation} checking={checking[row.key]} />
                      {row.validation?.description && <div className="missing-data__sub">{row.validation.description}</div>}
                      {row.validation?.messages?.length > 0 && row.validation.status !== 'ok' && <div className="missing-data__sub is-message">{row.validation.messages[0]}</div>}
                      {!row.validation && row.warnings?.length > 0 && <div className="missing-data__sub is-message">{row.warnings[0]}</div>}
                    </td>
                    <td>
                      {row.origin && row.origin !== 'manual' && <span className="missing-data__origin is-ai">{row.origin.replace('_', ' ')}</span>}
                      {row.origin === 'manual' && <span className="missing-data__origin">typed</span>}
                      {row.origin && row.origin !== 'manual' && row.note && <div className="missing-data__sub">{row.note}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <footer className="missing-data__footer">
          <span className="missing-data__message" role="status">
            {message || (invalid.length ? `${invalid.length} code${invalid.length === 1 ? ' is' : 's are'} invalid and will not be saved.` : '')}
          </span>
          {saveable.length > 0 && (
            <button type="button" className="missing-data__save" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : `Save to DB (${saveable.length})`}
            </button>
          )}
          <button type="button" className="missing-data__cancel" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default HsCodesModal
