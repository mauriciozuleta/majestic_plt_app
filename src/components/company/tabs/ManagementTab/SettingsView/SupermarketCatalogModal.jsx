import { useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelSupermarketCatalogJob,
  downloadSupermarketCatalog,
  fetchSupermarketCatalogJob,
  fetchSupermarketCatalogStatus,
  findSupermarketSubcategories,
  prepareSupermarketCatalog,
} from '../../../../../services/supermarketCatalog'
import './SupermarketCatalogModal.css'

const POLL_MS = 1200
// Category names that are fresh food — a quick selection, since a full
// supermarket catalog is mostly packaged goods the comparisons don't need.
const FRESH_FOOD = /fresh|produce|fruit|vegetable|veg\b|meat|seafood|fish|poultry|chicken|beef|pork|egg|dairy|deli|butcher|organic/i
const NOT_FRESH = /canned|tinned|dried|dry\b|juice|drink|snack|baby|sauce|soup|cereal|pet\b/i
const isFreshFood = (name) => FRESH_FOOD.test(name) && !NOT_FRESH.test(name)

// "Produce → Vegetables": a category's place in the store's hierarchy, when
// the catalog service saw its parents.
const categoryLabel = (category) => (category.path?.length ? category.path : [category.name]).join(' → ')

// Build a supermarket's catalog with the Supermarket_data_fetch service:
// web address + country -> its categories -> download the chosen ones; the
// exported file is then added to that country's product sources (Retail).
function SupermarketCatalogModal({ countries, initial, onClose, onImported }) {
  const [service, setService] = useState({ status: 'checking' })
  const [form, setForm] = useState({ country: initial?.country ?? '', url: initial?.url ?? '', name: initial?.name ?? '' })
  const [step, setStep] = useState('form') // form | preparing | categories | downloading | done
  const [job, setJob] = useState(null)
  const [prepared, setPrepared] = useState(null) // { store_id, store_name, categories }
  const [selected, setSelected] = useState(() => new Set())
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [imported, setImported] = useState(null)
  const [notice, setNotice] = useState('')
  // url of the category whose page is being checked for subcategories
  const [checkingUrl, setCheckingUrl] = useState(null)
  const timerRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    fetchSupermarketCatalogStatus()
      .then((data) => mountedRef.current && setService({ status: data.available ? 'ready' : 'down', detail: data.detail }))
      .catch((err) => mountedRef.current && setService({ status: 'down', detail: err.message }))
    return () => {
      mountedRef.current = false
      clearTimeout(timerRef.current)
    }
  }, [])

  const finish = (snapshot) => {
    if (snapshot.kind === 'subcategories') {
      setCheckingUrl(null)
      if (snapshot.status === 'done') {
        const { children, categories: merged, category } = snapshot.result
        setPrepared((prev) => ({ ...prev, categories: merged }))
        setNotice(children.length ? `Found ${children.length} subcategories in ${category.name}.` : `No subcategories found in ${category.name}.`)
      } else {
        setError(snapshot.status === 'cancelled' ? 'Cancelled.' : snapshot.error || 'Could not check that category.')
      }
      return
    }
    const back = snapshot.kind === 'prepare' ? 'form' : 'categories'
    if (snapshot.status === 'done' && snapshot.kind === 'prepare') {
      setPrepared(snapshot.result)
      setSelected(new Set())
      setForm((prev) => ({ ...prev, name: prev.name || snapshot.result.store_name || '' }))
      setStep('categories')
    } else if (snapshot.status === 'done' || (snapshot.status === 'cancelled' && snapshot.import)) {
      // A cancelled download still adds what it had collected.
      if (snapshot.import?.status === 'imported') {
        setImported(snapshot.import)
        setStep('done')
        onImported?.()
      } else {
        setError(snapshot.import?.error || 'The download finished, but its file could not be added.')
        setStep(back)
      }
    } else {
      setError(snapshot.status === 'cancelled' ? 'Cancelled.' : snapshot.error || 'The catalog service reported an error.')
      setStep(back)
    }
  }

  // Follows a job until it stops running.
  const follow = (snapshot) => {
    if (!mountedRef.current) return
    setJob(snapshot)
    if (snapshot.status !== 'running') {
      finish(snapshot)
      return
    }
    timerRef.current = setTimeout(async () => {
      try {
        follow(await fetchSupermarketCatalogJob(snapshot.id))
      } catch (err) {
        if (!mountedRef.current) return
        setError(err.message)
        if (snapshot.kind === 'subcategories') setCheckingUrl(null)
        else setStep(snapshot.kind === 'prepare' ? 'form' : 'categories')
      }
    }, POLL_MS)
  }

  const start = async (nextStep, call) => {
    setError('')
    setNotice('')
    setStep(nextStep)
    try {
      follow(await call())
    } catch (err) {
      setError(err.message)
      setStep(nextStep === 'preparing' ? 'form' : 'categories')
    }
  }

  const loadCategories = (event) => {
    event.preventDefault()
    start('preparing', () => prepareSupermarketCatalog({ url: form.url.trim(), country: form.country.trim() }))
  }

  const checkSubcategories = async (category) => {
    setError('')
    setNotice('')
    setCheckingUrl(category.url)
    try {
      follow(
        await findSupermarketSubcategories({
          store_id: prepared.store_id,
          category: { name: category.name, url: category.url },
          categories: prepared.categories,
        }),
      )
    } catch (err) {
      setCheckingUrl(null)
      setError(err.message)
    }
  }

  const download = () =>
    start('downloading', () =>
      downloadSupermarketCatalog({
        url: form.url.trim(),
        country: form.country.trim(),
        store_id: prepared.store_id,
        store_name: prepared.store_name,
        source_name: form.name.trim() || prepared.store_name,
        // Only {name, url} — the service's contract; the name carries the path.
        categories: prepared.categories
          .filter((category) => selected.has(category.url))
          .map((category) => ({ name: categoryLabel(category).replaceAll(' → ', ' > '), url: category.url })),
      }),
    )

  const cancel = () => job && cancelSupermarketCatalogJob(job.id).catch((err) => setError(err.message))

  const categories = useMemo(() => prepared?.categories ?? [], [prepared])
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return needle ? categories.filter((category) => categoryLabel(category).toLowerCase().includes(needle)) : categories
  }, [categories, filter])
  const toggle = (url) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(url)) next.delete(url)
      else next.add(url)
      return next
    })
  const selectMany = (items, on) =>
    setSelected((prev) => {
      const next = new Set(prev)
      items.forEach((category) => (on ? next.add(category.url) : next.delete(category.url)))
      return next
    })

  const running = step === 'preparing' || step === 'downloading' || checkingUrl != null
  const progress = job?.progress || {}
  const recentMessages = (job?.messages || []).slice(-5)

  return (
    <div className="supermarket-catalog__overlay" role="dialog" aria-modal="true" aria-label="Build supermarket catalog">
      <div className="supermarket-catalog">
        <header className="supermarket-catalog__header">
          <div>
            <span className="supermarket-catalog__eyebrow">Supermarket catalog</span>
            <h3>{prepared?.store_name || 'Build from a supermarket website'}</h3>
          </div>
          <button type="button" className="supermarket-catalog__close" onClick={onClose} aria-label="Close" disabled={running}>
            ×
          </button>
        </header>

        {service.status === 'checking' && <p className="supermarket-catalog__hint">Checking the catalog service…</p>}
        {service.status === 'down' && <p className="supermarket-catalog__error">{service.detail}</p>}
        {error && <p className="supermarket-catalog__error">{error}</p>}
        {notice && <p className="supermarket-catalog__hint">{notice}</p>}

        {service.status === 'ready' && (step === 'form' || step === 'preparing') && (
          <form className="supermarket-catalog__form" onSubmit={loadCategories}>
            <label>
              Country
              <input
                list="supermarket-catalog-countries"
                value={form.country}
                onChange={(event) => setForm((prev) => ({ ...prev, country: event.target.value }))}
                placeholder="e.g. Barbados"
                required
                disabled={running}
              />
              <datalist id="supermarket-catalog-countries">
                {countries.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            </label>
            <label className="supermarket-catalog__wide">
              Supermarket web address
              <input
                value={form.url}
                onChange={(event) => setForm((prev) => ({ ...prev, url: event.target.value }))}
                placeholder="https://… — the store's home page or a category page"
                required
                disabled={running}
              />
            </label>
            <div className="supermarket-catalog__actions">
              <button type="submit" className="settings-view__btn" disabled={running}>
                {step === 'preparing' ? 'Loading categories…' : 'Load categories'}
              </button>
              {step === 'preparing' && (
                <button type="button" className="settings-view__btn" onClick={cancel}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        )}

        {(step === 'categories' || step === 'downloading') && prepared && (
          <>
            <div className="supermarket-catalog__form">
              <label>
                Source name
                <input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} disabled={running} />
              </label>
              <label>
                Find a category
                <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="e.g. fruit" disabled={running} />
              </label>
            </div>
            <div className="supermarket-catalog__toolbar">
              <span>
                {categories.length} categories · {selected.size} selected
              </span>
              <button type="button" onClick={() => selectMany(categories.filter((category) => isFreshFood(categoryLabel(category))), true)} disabled={running}>
                Select fresh food
              </button>
              <button type="button" onClick={() => selectMany(visible, true)} disabled={running}>
                Select {filter ? 'shown' : 'all'}
              </button>
              <button type="button" onClick={() => selectMany(visible, false)} disabled={running}>
                Clear {filter ? 'shown' : 'all'}
              </button>
            </div>
            <ul className="supermarket-catalog__list">
              {visible.map((category) => (
                <li key={category.url}>
                  <label title={category.url}>
                    <input type="checkbox" checked={selected.has(category.url)} onChange={() => toggle(category.url)} disabled={running} />
                    <span>
                      {categoryLabel(category)}
                      {category.subcategory_count ? <em> ({category.subcategory_count})</em> : null}
                    </span>
                  </label>
                  <button
                    type="button"
                    className="supermarket-catalog__sub-btn"
                    onClick={() => checkSubcategories(category)}
                    disabled={running}
                    title="Check this category's page for sections inside it"
                  >
                    {checkingUrl === category.url ? 'Checking…' : 'Subcategories'}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {running && (
          <div className="supermarket-catalog__progress">
            {step === 'downloading' && progress.categories_total != null && (
              <p>
                <strong>
                  {progress.categories_completed} of {progress.categories_total} categories
                </strong>{' '}
                · {progress.products ?? 0} products collected
                {progress.errors ? ` · ${progress.errors} failed` : ''}
              </p>
            )}
            {step === 'downloading' && String(progress.message || '').startsWith('Images:') && (
              <p>
                Saving product images — {progress.message.replace('Images:', '').split(',')[0].trim()}
              </p>
            )}
            <ul>
              {recentMessages.map((message) => (
                <li key={message.at + message.text}>{message.text}</li>
              ))}
            </ul>
          </div>
        )}

        {step === 'done' && imported && (
          <div className="supermarket-catalog__done">
            <p>
              Added <strong>{imported.product_count} products</strong> to {imported.source.country_name} ▸ {imported.source.name} (Retail).
            </p>
            {imported.images && (
              <p className="supermarket-catalog__hint">
                {imported.images.downloaded} of {imported.images.total} product images saved with the file.
              </p>
            )}
            {imported.source.status_message && <p className="supermarket-catalog__hint">{imported.source.status_message}</p>}
          </div>
        )}

        <footer className="supermarket-catalog__footer">
          {step === 'categories' && (
            <button type="button" className="settings-view__btn" onClick={download} disabled={selected.size === 0}>
              Download {selected.size || ''} selected
            </button>
          )}
          {step === 'downloading' && (
            <button type="button" className="settings-view__btn" onClick={cancel}>
              Cancel download
            </button>
          )}
          <button type="button" className="settings-view__btn" onClick={onClose} disabled={running}>
            {step === 'done' ? 'Done' : 'Close'}
          </button>
        </footer>
      </div>
    </div>
  )
}

export default SupermarketCatalogModal
