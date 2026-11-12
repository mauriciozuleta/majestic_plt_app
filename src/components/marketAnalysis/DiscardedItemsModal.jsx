import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchScopeItems, fetchScopeSummary, moveScopeItems } from '../../services/catalogScope'
import './MissingDataModal.css'

const money = (value, currency) => (value == null ? '—' : `${currency ? `${currency} ` : ''}${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`)
const rowKey = (item) => `${item.source}|${item.name.toLowerCase()}`

const VIEWS = {
  secondary: { title: 'Discarded products', option: 'Discarded list', hint: 'Downloaded products kept out of the main catalog: fresh produce, meat, fish, cheese and eggs are in; other dairy, canned meat, frozen or dried produce, bakery, drinks, sauces and non-food are out. Nothing is deleted: tick any product and return it to the catalog.', action: 'Return to catalog', to: 'main', done: 'returned to the catalog', empty: (country) => `Nothing was discarded for ${country}.` },
  check: { title: 'Products to check', option: 'To check', hint: 'Catalog products with something still open: no HS code, an old one (not in HS 2022), no price per kg yet, or the rules were not sure they belong. Fix the open item, or tick a product that does not belong and set it aside.', action: 'Set aside', to: 'secondary', done: 'set aside', empty: (country) => `Nothing to check for ${country}.` },
  ready: { title: 'Catalog products', option: 'Catalog', hint: 'Catalog products with nothing open. Tick any product that does not belong and set it aside.', action: 'Set aside', to: 'secondary', done: 'set aside', empty: () => 'No products match.' },
}

// One of the three portfolios of a country, as a list (the secondary / discarded list, the products to check, the ready catalog): what the catalog scope decided on the server
// (backend/catalog_normalization/scope.py, scope_store.py) with the reason or the open issues, and the move between the lists. Nothing is deleted; the choice is saved and kept when the
// catalog is downloaded again. Used inline by the country's product page (tabs) and inside a modal by the Market Analysis table.
export function ScopeItemsPanel({ country, view: initialView = 'secondary', allowViewSwitch = false, onChanged }) {
  const [view, setView] = useState(initialView)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [state, setState] = useState('loading')
  const [filter, setFilter] = useState('')
  const [reason, setReason] = useState('')
  const [reasons, setReasons] = useState([])
  const [ticked, setTicked] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const config = VIEWS[view]

  const load = useCallback(() => {
    let cancelled = false
    setState('loading')
    fetchScopeItems({ status: view, country, query: filter.trim(), reason: view === 'secondary' ? reason : '', limit: 500 })
      .then((data) => {
        if (cancelled) return
        setItems(data.items)
        setTotal(data.total)
        setState('ready')
      })
      .catch((error) => !cancelled && setState(error.message || 'error'))
    return () => {
      cancelled = true
    }
  }, [view, country, filter, reason])

  useEffect(() => {
    const timer = setTimeout(load, filter ? 300 : 0) // a typed filter waits for a pause
    return () => clearTimeout(timer)
  }, [load, filter])

  useEffect(() => {
    fetchScopeSummary()
      .then((data) => setReasons(Object.keys(data.reasons)))
      .catch(() => {})
  }, [])

  const shownKeys = useMemo(() => items.map(rowKey), [items])
  const allTicked = shownKeys.length > 0 && shownKeys.every((key) => ticked.has(key))
  const toggle = (key) =>
    setTicked((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const toggleAll = () => setTicked(allTicked ? new Set() : new Set(shownKeys))

  const move = async () => {
    const picked = items.filter((item) => ticked.has(rowKey(item)))
    if (!picked.length) return
    setBusy(true)
    setMessage('')
    try {
      const result = await moveScopeItems(picked.map((item) => ({ source: item.source, name: item.name })), config.to)
      setMessage(`${result.moved} product${result.moved === 1 ? '' : 's'} ${config.done}.`)
      setTicked(new Set())
      onChanged?.()
      load()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="scope-panel">
      <p className="scope-panel__hint">
        {config.hint} Showing {items.length} of {total}.
      </p>
      <div className="missing-data__toolbar">
        <input type="search" placeholder="Filter products" value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter products" />
        {allowViewSwitch && (
          <select value={view} onChange={(event) => { setView(event.target.value); setTicked(new Set()) }} aria-label="List">
            {Object.entries(VIEWS).map(([key, item]) => (
              <option key={key} value={key}>
                {item.option}
              </option>
            ))}
          </select>
        )}
        {view === 'secondary' && (
          <select value={reason} onChange={(event) => setReason(event.target.value)} aria-label="Reason">
            <option value="">All reasons</option>
            {reasons.map((text) => (
              <option key={text} value={text}>
                {text}
              </option>
            ))}
          </select>
        )}
        <span className="missing-data__count">{ticked.size} ticked</span>
        {ticked.size > 0 && (
          <button type="button" className="missing-data__save" onClick={move} disabled={busy}>
            {busy ? 'Moving…' : `${config.action} (${ticked.size})`}
          </button>
        )}
      </div>
      {message && (
        <p className="missing-data__message" role="status">
          {message}
        </p>
      )}

      <div className="missing-data__body">
        {state === 'loading' && <p className="missing-data__hint">Loading…</p>}
        {state !== 'loading' && state !== 'ready' && <p className="missing-data__error">{state}</p>}
        {state === 'ready' && items.length === 0 && <p className="missing-data__hint">{config.empty(country)}</p>}
        {state === 'ready' && items.length > 0 && (
          <table className="missing-data__table">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" checked={allTicked} onChange={toggleAll} aria-label="Tick all shown" />
                </th>
                <th>Product</th>
                <th>Sold as</th>
                <th>HS</th>
                <th>{view === 'check' ? 'To fix' : 'Why'}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={rowKey(item)}>
                  <td>
                    <input type="checkbox" checked={ticked.has(rowKey(item))} onChange={() => toggle(rowKey(item))} aria-label={`Tick ${item.name}`} />
                  </td>
                  <td>
                    <div className="missing-data__name">{item.name}</div>
                    <div className="missing-data__sub">
                      {item.category || '—'} · {item.source_name}
                    </div>
                  </td>
                  <td>
                    <div className="missing-data__sub">
                      {item.unit || '—'} · {money(item.price, item.currency)}
                    </div>
                  </td>
                  <td>
                    <div className="missing-data__sub">{item.hs6 || 'no code'}</div>
                  </td>
                  <td>
                    {view === 'check' ? (
                      item.issues.map((issue) => (
                        <div key={issue.code} className="missing-data__sub">
                          {issue.label}
                        </div>
                      ))
                    ) : (
                      <div className="missing-data__sub">{item.reason}</div>
                    )}
                    {item.rule === 'override' && <span className="missing-data__origin">moved by you</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// The same list in a modal: opened by the "N discarded" pill of the Market Analysis table. The list switch also reaches the other two portfolios.
function DiscardedItemsModal({ country, onClose, onChanged }) {
  return (
    <div className="missing-data__overlay" role="dialog" aria-modal="true" aria-label={`Product portfolios of ${country}`}>
      <div className="missing-data">
        <header className="missing-data__header">
          <div>
            <h3>Discarded products — {country}</h3>
          </div>
          <button type="button" className="missing-data__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <ScopeItemsPanel country={country} view="secondary" allowViewSwitch onChanged={onChanged} />
        <footer className="missing-data__footer">
          <button type="button" className="missing-data__cancel" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default DiscardedItemsModal
