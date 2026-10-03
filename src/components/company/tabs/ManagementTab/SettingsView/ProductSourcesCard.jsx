import { useEffect, useRef, useState } from 'react'
import {
  createProductSource,
  deleteProductSource,
  fetchProductSources,
  loadProductSourceFile,
  refreshProductSource,
  setSourceAnalysisType,
  updateProductSource,
} from '../../../../../services/productSources'
import { fetchCommercialCountries } from '../../../../../services/commercialStructure'
import { useAppStore } from '../../../../../store/useAppStore'
import SupermarketCatalogModal from './SupermarketCatalogModal'
import './ProductSourcesCard.css'

const EMPTY_FORM = { country_name: '', name: '', url: '', currency: '', analysis_type: 'wholesaler' }
const FILE_ACCEPT = '.csv,.xlsx,.xlsm,.pdf'

function formatWhen(iso) {
  if (!iso) return 'never'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'never' : date.toLocaleString()
}

function statusOf(source) {
  if (source.status === 'ok') return { tone: 'ok', label: `${source.product_count} products` }
  if (source.status === 'needs_file') return { tone: 'warn', label: 'Needs a file' }
  return { tone: 'idle', label: source.built_in ? 'Not fetched yet' : 'No products yet' }
}

function SourceForm({ initial, countries, busy, submitLabel, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial)
  const set = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))

  return (
    <form
      className="product-sources__form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(form)
      }}
    >
      <label>
        Country
        <input list="product-source-countries" value={form.country_name} onChange={set('country_name')} placeholder="e.g. Ecuador" required />
        <datalist id="product-source-countries">
          {countries.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>
      <label>
        Source name
        <input value={form.name} onChange={set('name')} placeholder="e.g. Mercado Mayorista Quito" required />
      </label>
      <label className="product-sources__form-wide">
        Web address (optional)
        <input value={form.url} onChange={set('url')} placeholder="https://… — the page is analysed and its prices downloaded" />
      </label>
      <label>
        Currency (optional)
        <input value={form.currency} onChange={set('currency')} placeholder="USD" maxLength={6} />
      </label>
      <div className="product-sources__form-wide product-sources__direction">
        <span className="product-sources__direction-label">Price level</span>
        <label className="product-sources__checkbox">
          <input
            type="checkbox"
            checked={form.analysis_type === 'wholesaler'}
            onChange={() => setForm((prev) => ({ ...prev, analysis_type: 'wholesaler' }))}
          />
          Wholesaler
        </label>
        <label className="product-sources__checkbox">
          <input
            type="checkbox"
            checked={form.analysis_type === 'retail'}
            onChange={() => setForm((prev) => ({ ...prev, analysis_type: 'retail' }))}
          />
          Retail
        </label>
      </div>
      <div className="product-sources__form-actions">
        <button type="submit" className="settings-view__btn" disabled={busy}>
          {busy ? 'Analysing…' : submitLabel}
        </button>
        <button type="button" className="settings-view__btn" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
      {!form.url.trim() && <p className="product-sources__hint product-sources__form-wide">Without a web address you'll load a products file (csv, xlsx or pdf) instead.</p>}
    </form>
  )
}

function SourceRow({ source, busy, rowError, onRefresh, onRebuild, onLoadFile, onEdit, onDelete, onSetAnalysisType }) {
  const status = statusOf(source)
  return (
    <div className="product-sources__row">
      <div className="product-sources__main">
        <div className="product-sources__title">
          <strong>{source.name}</strong>
          {source.built_in && <span className="product-sources__badge">Built-in</span>}
          {source.origin === 'catalog' && <span className="product-sources__badge">Supermarket catalog</span>}
          <div className="product-sources__direction product-sources__direction--inline">
            <label className="product-sources__checkbox">
              <input
                type="checkbox"
                checked={source.analysis_type === 'wholesaler'}
                onChange={() => onSetAnalysisType(source, 'wholesaler')}
                disabled={busy}
              />
              Wholesaler
            </label>
            <label className="product-sources__checkbox">
              <input
                type="checkbox"
                checked={source.analysis_type === 'retail'}
                onChange={() => onSetAnalysisType(source, 'retail')}
                disabled={busy}
              />
              Retail
            </label>
          </div>
          <span className={`product-sources__status product-sources__status--${status.tone}`}>{status.label}</span>
        </div>
        <div className="product-sources__meta">
          {source.url ? (
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.url}
            </a>
          ) : (
            <span>No web address — products come from a file</span>
          )}
          <span>Last loaded: {formatWhen(source.last_loaded_at)}</span>
          {source.currency && <span>Currency: {source.currency}</span>}
        </div>
        {source.status_message && <p className={`product-sources__note product-sources__note--${status.tone}`}>{source.status_message}</p>}
        {rowError && <p className="product-sources__note product-sources__note--warn">{rowError}</p>}
        {busy && <p className="product-sources__hint">Working…</p>}
        {source.built_in && <p className="product-sources__hint">Updated from the Country Product Portfolio tab's Update button.</p>}
      </div>

      {!source.built_in && (
        <div className="product-sources__actions">
          {source.origin === 'catalog' ? (
            <button type="button" className="settings-view__btn" onClick={() => onRebuild(source)} disabled={busy}>
              Rebuild catalog
            </button>
          ) : (
            source.url && (
              <button type="button" className="settings-view__btn" onClick={() => onRefresh(source)} disabled={busy}>
                {busy ? 'Working…' : 'Refresh'}
              </button>
            )
          )}
          <button type="button" className="settings-view__btn" onClick={() => onLoadFile(source)} disabled={busy}>
            {busy ? 'Loading…' : 'Load file'}
          </button>
          <button type="button" className="settings-view__btn" onClick={() => onEdit(source)} disabled={busy}>
            Edit
          </button>
          <button type="button" className="settings-view__btn product-sources__danger" onClick={() => onDelete(source)} disabled={busy}>
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

function ProductSourcesCard() {
  const [expanded, setExpanded] = useState(false)
  const [sources, setSources] = useState({ built_in: [], custom: [] })
  const [status, setStatus] = useState('loading')
  const [companyCountries, setCompanyCountries] = useState([])
  const [mode, setMode] = useState(null) // null | 'add' | source being edited
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const [errorId, setErrorId] = useState(null)
  const fileInputRef = useRef(null)
  const fileTargetRef = useRef(null)
  // null, or the initial { country, url, name } of the supermarket catalog being built
  const [catalogBuild, setCatalogBuild] = useState(null)

  const reload = () =>
    fetchProductSources()
      .then((data) => {
        setSources(data)
        setStatus('ready')
      })
      .catch(() => setStatus('error'))

  useEffect(() => {
    if (!expanded) return
    reload()
    // Countries already in a company's commercial structure — suggestions
    // for the country field; any name can still be typed.
    Promise.all(useAppStore.getState().companies.map((company) => fetchCommercialCountries(company.id).catch(() => [])))
      .then((lists) => setCompanyCountries([...new Set(lists.flat().map((country) => country.name))].sort()))
      .catch(() => setCompanyCountries([]))
  }, [expanded])

  const run = async (id, action) => {
    setBusyId(id)
    setError('')
    setErrorId(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setError(err.message)
      setErrorId(id)
    } finally {
      setBusyId(null)
    }
  }

  const handleSubmit = (form) => {
    const payload = { ...form, url: form.url.trim() || null, currency: form.currency.trim() || null }
    const editing = mode && mode !== 'add' ? mode : null
    return run(editing ? editing.id : 'new', async () => {
      if (editing) await updateProductSource(editing.id, payload)
      else await createProductSource(payload)
      setMode(null)
    })
  }

  const pickFile = (source) => {
    fileTargetRef.current = source
    fileInputRef.current?.click()
  }

  const handleFile = (event) => {
    const file = event.target.files?.[0]
    const source = fileTargetRef.current
    event.target.value = ''
    if (!file || !source) return
    run(source.id, () => loadProductSourceFile(source.id, file))
  }

  const handleDelete = (source) => {
    if (!window.confirm(`Delete "${source.name}" and its ${source.product_count} loaded products?`)) return
    run(source.id, () => deleteProductSource(source.id))
  }

  const handleSetAnalysisType = (source, analysisType) => {
    if (source.analysis_type === analysisType) return
    run(source.id, () => setSourceAnalysisType(source.id, analysisType))
  }

  const countrySuggestions = [...new Set(['Colombia', 'United States', ...companyCountries, ...sources.custom.map((s) => s.country_name)])].sort()
  const grouped = [...sources.built_in, ...sources.custom].reduce((groups, source) => {
    ;(groups[source.country_name] ||= []).push(source)
    return groups
  }, {})

  return (
    <div className="settings-view__card">
      <button type="button" className="settings-view__card-toggle" onClick={() => setExpanded((prev) => !prev)} aria-expanded={expanded}>
        <span className={`settings-view__tax-chevron ${expanded ? 'is-expanded' : ''}`}>▸</span>
        <div className="settings-view__section-heading">
          <h4>Product analysis sources</h4>
          <p>Where each country's product prices come from. Add a source by web address, or load a products file.</p>
        </div>
      </button>

      {expanded && (
        <>
          <input ref={fileInputRef} type="file" accept={FILE_ACCEPT} style={{ display: 'none' }} onChange={handleFile} />

          {mode ? (
            <SourceForm
              key={mode === 'add' ? 'add' : mode.id}
              initial={
                mode === 'add'
                  ? EMPTY_FORM
                  : {
                      country_name: mode.country_name,
                      name: mode.name,
                      url: mode.url || '',
                      currency: mode.currency || '',
                      analysis_type: mode.analysis_type || 'wholesaler',
                    }
              }
              countries={countrySuggestions}
              busy={busyId === 'new' || (mode !== 'add' && busyId === mode.id)}
              submitLabel={mode === 'add' ? 'Add source' : 'Save changes'}
              onSubmit={handleSubmit}
              onCancel={() => setMode(null)}
            />
          ) : (
            <div className="product-sources__add-actions">
              <button type="button" className="settings-view__btn" onClick={() => setMode('add')}>
                + Add source
              </button>
              <button type="button" className="settings-view__btn" onClick={() => setCatalogBuild({})}>
                + Build supermarket catalog
              </button>
            </div>
          )}

          {error && <p className="product-sources__note product-sources__note--warn">{error}</p>}
          {status === 'loading' && <p className="product-sources__hint">Loading…</p>}
          {status === 'error' && <p className="product-sources__note product-sources__note--warn">Could not load the sources.</p>}

          {status === 'ready' &&
            Object.entries(grouped).map(([country, list]) => (
              <section key={country} className="product-sources__group">
                <h5>{country}</h5>
                {list.map((source) => (
                  <SourceRow
                    key={source.id}
                    source={source}
                    busy={busyId === source.id}
                    rowError={errorId === source.id ? error : null}
                    onRefresh={(item) => run(item.id, () => refreshProductSource(item.id))}
                    onRebuild={(item) => setCatalogBuild({ country: item.country_name, url: item.url || '', name: item.name })}
                    onLoadFile={pickFile}
                    onEdit={setMode}
                    onDelete={handleDelete}
                    onSetAnalysisType={handleSetAnalysisType}
                  />
                ))}
              </section>
            ))}
        </>
      )}
      {catalogBuild && (
        <SupermarketCatalogModal
          countries={countrySuggestions}
          initial={catalogBuild}
          onClose={() => setCatalogBuild(null)}
          onImported={reload}
        />
      )}
    </div>
  )
}

export default ProductSourcesCard
