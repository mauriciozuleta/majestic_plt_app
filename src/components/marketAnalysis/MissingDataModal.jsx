import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ESTIMATED_USD_PER_PRODUCT, fetchMissingItems, saveWeights, suggestWeights, validateWeights } from '../../services/catalogNormalization'
import './MissingDataModal.css'

const AI_BATCH = 12 // the backend researches at most this many products per call
const UNIT_WORDS = { each: 'item', bunch: 'bunch', head: 'head', sleeve: 'sleeve', dozen: 'dozen', pack: 'pack' }
const num = (value) => (value === '' || value == null || Number.isNaN(Number(value)) ? null : Number(value))
const round = (value) => (value == null ? '' : String(Math.round(value * 10) / 10))
const SOURCE_LABELS = { la_mayorista: 'La Mayorista', corabastos: 'Corabastos', usa_retail_produce: 'USDA retail' }
const sourceLabel = (key) => SOURCE_LABELS[key] || (key.startsWith('usa_') ? 'USDA' : '')
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

// The form behind the red "need data" pill of Market Analysis ▸ Country Product Portfolio: every product of the country whose unit-priced listings ("each", "per bunch", a counted bag)
// have no weight of one item yet. The person types the weights, or presses "AI Search" to have the AI research the blanks on the web; every value, typed or suggested, is checked
// (plausible range, USDA's published weight, the price per kg it produces against the same product's other listings) and "Save to DB" stores the valid ones and updates the pills.
function MissingDataModal({ country, onClose, onSaved }) {
  const [rows, setRows] = useState([])
  const [loadState, setLoadState] = useState('loading')
  const [filter, setFilter] = useState('')
  const [aiState, setAiState] = useState({ running: false, done: 0, total: 0, error: '' })
  const [checking, setChecking] = useState({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const timers = useRef({})

  useEffect(() => {
    let cancelled = false
    fetchMissingItems(country)
      .then((items) => {
        if (cancelled) return
        setRows(items.map((item) => ({ ...item, key: `${item.name}|${item.count_unit}`, weight: '', min: '', max: '', origin: null, confidence: null, note: '', sources: [], validation: null })))
        setLoadState('ready')
      })
      .catch((error) => !cancelled && setLoadState(error.message || 'error'))
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

  // a typed value is checked shortly after the person stops typing
  const validateLater = useCallback(
    (row, weight, min, max) => {
      clearTimeout(timers.current[row.key])
      if (num(weight) == null) {
        patchRow(row.key, { validation: null })
        return
      }
      setChecking((previous) => ({ ...previous, [row.key]: true }))
      timers.current[row.key] = setTimeout(() => {
        validateWeights([{ name: row.name, count_unit: row.count_unit, weight_g: num(weight), min_g: num(min), max_g: num(max) }])
          .then(([validation]) => patchRow(row.key, { validation }))
          .catch(() => patchRow(row.key, { validation: { status: 'warning', messages: ['The value could not be checked.'], previews: [] } }))
          .finally(() => setChecking((previous) => ({ ...previous, [row.key]: false })))
      }, 500)
    },
    [patchRow],
  )

  const edit = (row, field, value) => {
    const next = { ...row, [field]: value, origin: 'manual', note: '', sources: [], confidence: null }
    patchRow(row.key, { [field]: value, origin: 'manual', note: '', sources: [], confidence: null })
    validateLater(row, next.weight, next.min, next.max)
  }

  const blanks = rows.filter((row) => num(row.weight) == null)

  const aiSearch = async () => {
    const targets = rows.filter((row) => num(row.weight) == null)
    if (!targets.length || aiState.running) return
    // this spends Anthropic credits (about 0.09 USD per product, one web research each): the person sees the amount and accepts it
    const estimate = Math.round(targets.length * ESTIMATED_USD_PER_PRODUCT * 100) / 100
    if (!window.confirm(`AI Search will research ${targets.length} product${targets.length === 1 ? '' : 's'} on the web with Claude.\n\nEstimated cost: about $${estimate.toFixed(2)} of Anthropic credits.\n\nTyping the weights yourself is free. Continue?`)) return
    setMessage('')
    setAiState({ running: true, done: 0, total: targets.length, error: '' })
    try {
      for (let start = 0; start < targets.length; start += AI_BATCH) {
        const batch = targets.slice(start, start + AI_BATCH)
        // eslint-disable-next-line no-await-in-loop -- one web-research call at a time
        const results = await suggestWeights(batch, Math.round(batch.length * ESTIMATED_USD_PER_PRODUCT * 100) / 100)
        results.forEach((result, index) => {
          const row = batch[index]
          if (result.weight_g == null) {
            patchRow(row.key, { note: result.note || 'The AI found no reliable weight for this product.', origin: null, validation: result.validation })
            return
          }
          patchRow(row.key, { weight: round(result.weight_g), min: round(result.min_g), max: round(result.max_g), origin: 'ai', confidence: result.confidence, note: result.note, sources: result.sources, validation: result.validation })
        })
        setAiState((previous) => ({ ...previous, done: Math.min(start + AI_BATCH, targets.length) }))
      }
      setAiState((previous) => ({ ...previous, running: false }))
    } catch (error) {
      setAiState((previous) => ({ ...previous, running: false, error: error.message || 'The AI search failed.' }))
    }
  }

  const filled = rows.filter((row) => num(row.weight) != null)
  const saveable = filled.filter((row) => row.validation && row.validation.status !== 'error' && !checking[row.key])
  const invalid = filled.filter((row) => row.validation?.status === 'error')

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const result = await saveWeights(
        saveable.map((row) => ({
          name: row.name, count_unit: row.count_unit, weight_g: num(row.weight), min_g: num(row.min), max_g: num(row.max),
          origin: row.origin === 'ai' ? 'ai' : 'manual', confidence: row.confidence, note: row.origin === 'ai' ? row.note : '', sources: row.sources,
        })),
      )
      const savedKeys = new Set(saveable.map((row) => row.key))
      setRows((previous) => previous.filter((row) => !savedKeys.has(row.key) || result.refused.some((item) => item.name === row.name)))
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
    <div className="missing-data__overlay" role="dialog" aria-modal="true" aria-label={`Missing product data for ${country}`} onClick={onClose}>
      <div className="missing-data" onClick={(event) => event.stopPropagation()}>
        <header className="missing-data__header">
          <div>
            <h3>Missing product data — {country}</h3>
            <p>
              These products are priced per unit (each, per bunch, a counted bag), so they cannot be compared per kilo until the weight of <strong>one item</strong> is known. Type it,
              or let the AI search the web for the blanks. Every value is checked before it can be saved.
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
          <button type="button" className="missing-data__ai" onClick={aiSearch} disabled={aiState.running || !blanks.length} title="The AI researches on the web the weight of one item for every blank. Nothing is saved until you press Save to DB.">
            {aiState.running ? `AI searching… ${aiState.done}/${aiState.total}` : `AI Search (${blanks.length}, about $${(blanks.length * ESTIMATED_USD_PER_PRODUCT).toFixed(2)})`}
          </button>
        </div>
        {aiState.error && <p className="missing-data__error">AI Search: {aiState.error}</p>}

        <div className="missing-data__body">
          {loadState === 'loading' && <p className="missing-data__hint">Loading…</p>}
          {loadState !== 'loading' && loadState !== 'ready' && <p className="missing-data__error">{loadState}</p>}
          {loadState === 'ready' && rows.length === 0 && <p className="missing-data__hint">Nothing is missing for {country}.</p>}
          {loadState === 'ready' && rows.length > 0 && (
            <table className="missing-data__table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Sold as</th>
                  <th className="is-num">Weight of one item (g)</th>
                  <th className="is-num">Typical range (g)</th>
                  <th>Check</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <div className="missing-data__name">{row.name}</div>
                      <div className="missing-data__sub">{row.rows} listing{row.rows === 1 ? '' : 's'}</div>
                    </td>
                    <td>
                      {row.examples.slice(0, 2).map((example) => (
                        <div key={`${example.source}|${example.label}`} className="missing-data__sub">
                          {example.unit_text || '—'} · {money(example.price)}
                        </div>
                      ))}
                      <div className="missing-data__sub">per {UNIT_WORDS[row.count_unit] || row.count_unit}</div>
                    </td>
                    <td className="is-num">
                      <input type="number" min="0" step="any" inputMode="decimal" value={row.weight} onChange={(event) => edit(row, 'weight', event.target.value)} aria-label={`Weight of one ${row.name} in grams`} />
                    </td>
                    <td className="is-num missing-data__range">
                      <input type="number" min="0" step="any" value={row.min} onChange={(event) => edit(row, 'min', event.target.value)} aria-label={`Lowest weight of ${row.name}`} placeholder="min" />
                      <input type="number" min="0" step="any" value={row.max} onChange={(event) => edit(row, 'max', event.target.value)} aria-label={`Highest weight of ${row.name}`} placeholder="max" />
                    </td>
                    <td>
                      <StatusPill validation={row.validation} checking={checking[row.key]} />
                      {row.validation?.previews?.slice(0, 2).map((preview) => (
                        <div key={preview.source} className="missing-data__sub">
                          = {money(preview.price_per_kg)} / kg{sourceLabel(preview.source) ? ` · ${sourceLabel(preview.source)}` : ''}
                        </div>
                      ))}
                      {row.validation?.messages?.length > 0 && row.validation.status !== 'ok' && <div className="missing-data__sub is-message">{row.validation.messages[0]}</div>}
                    </td>
                    <td>
                      {row.origin === 'ai' && (
                        <>
                          <span className="missing-data__origin is-ai">AI · {row.confidence || '?'}</span>
                          {row.note && <div className="missing-data__sub">{row.note}</div>}
                          {row.sources?.slice(0, 2).map((url) => (
                            <a key={url} className="missing-data__source" href={url} target="_blank" rel="noreferrer">
                              source
                            </a>
                          ))}
                        </>
                      )}
                      {row.origin === 'manual' && <span className="missing-data__origin">typed</span>}
                      {!row.origin && row.note && <div className="missing-data__sub">{row.note}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <footer className="missing-data__footer">
          <span className="missing-data__message" role="status">
            {message || (invalid.length ? `${invalid.length} value${invalid.length === 1 ? ' is' : 's are'} invalid and will not be saved.` : '')}
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

export default MissingDataModal
