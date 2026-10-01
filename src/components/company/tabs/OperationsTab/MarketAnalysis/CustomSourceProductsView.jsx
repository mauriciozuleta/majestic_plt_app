import { useEffect, useMemo, useState } from 'react'
import { fetchCustomSourceProducts, refreshProductSource } from '../../../../../services/productSources'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import { fetchReferenceCountries } from '../../../../../services/commercialStructure'
import { buildProductCodeIndex } from '../../../../../services/productPortfolio'
import { fetchWeightResearch, researchMissingWeights } from '../../../../../services/weightResearch'
import { clearCustomOverride, fetchCustomOverrides, saveCustomOverride } from '../../../../../services/productOverrides'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { formatOneUsdEquals, formatPriceLine } from './priceFormat'
import { explainGenericConversion, genericPricePerKg, genericWeightResearchItem } from './genericUnitConversion'
import { applyCustomOverride, applyResearchedWeight } from './unitConversion'
import './ColombiaProductAnalysisView.css'

const ISO_CURRENCY_RE = /^[A-Z]{3}$/

// A source named with its own web address reads as just its domain; the full
// address stays available as a tooltip.
function displaySourceName(name) {
  try {
    return new URL(name).hostname.replace(/^www\./, '')
  } catch {
    return name
  }
}

function priceLevelLabel(analysisType) {
  return analysisType === 'retail' ? 'Retail' : 'Wholesaler'
}

function timeLabel(date) {
  if (!date) return null
  const datePart = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const timePart = date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return `${datePart}, ${timePart}`
}

function SourceStatus({ label, sync }) {
  const badgeClass =
    sync.status === 'loading' ? 'is-loading' : sync.status === 'fresh' ? 'is-fresh' : sync.status === 'stale' ? 'is-stale' : 'is-never'
  const badgeText = sync.status === 'loading' ? 'Updating…' : sync.status === 'fresh' ? 'Fresh' : sync.status === 'stale' ? 'Stale' : 'Not loaded'
  return (
    <div className="price-comparison__source-status">
      <span className="price-comparison__source-name">{label}</span>
      <span className={`price-comparison__status-badge ${badgeClass}`} title={sync.status === 'stale' ? sync.error || undefined : undefined}>
        {badgeText}
      </span>
      {sync.lastSyncedAt && <span className="price-comparison__synced-at">Synced {timeLabel(sync.lastSyncedAt)}</span>}
    </div>
  )
}

// USD first with the local amount alongside — the same "US$3.60 (COP$12,000)"
// line the Colombia/USA tables use.
function priceLine(localValue, currency, usdRates) {
  if (localValue === null || localValue === undefined) return '—'
  if (currency === 'USD') return formatPriceLine(localValue, null, null)
  if (!currency) return Number(localValue).toLocaleString('en-US', { maximumFractionDigits: 2 })
  // Cents kept on the local side — unlike COP, these currencies (JMD, XCD,
  // TTD…) quote real fractional prices (XCD 21.95, not 22).
  const local = `${currency}$${Number(localValue).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const rate = usdRates[currency]
  return rate ? `${formatPriceLine(localValue * rate, null, null)} (${local})` : local
}

function rowSignature(row) {
  return `custom-row:${row.sourceId}:${row.category}:${row.name.toLowerCase()}:${row.unit}`
}

// Products from every source added in Settings ▸ Product analysis sources for
// one country, laid out exactly like the Colombia/USA tables: same header,
// source status, currency line, category chips, stats and the same twelve
// columns, with per-kg conversion via genericUnitConversion.js, AI weight
// research and custom overrides. Under Colombia/USA (showEmptyHint=false) it
// renders as an extra "Added sources" block beside the built-in table.
// `highlightHsCode` filters to products whose reference code (country ISO2 +
// HS code, see productPortfolio.js) falls under that HS code; the parent
// remounts this view on every new click, so seeding state from it is enough.
function CustomSourceProductsView({ countryName, companyId, showEmptyHint = true, highlightHsCode = null }) {
  const [sources, setSources] = useState([])
  const [status, setStatus] = useState('loading')
  const [syncBySource, setSyncBySource] = useState({})
  const [countryCurrency, setCountryCurrency] = useState(null)
  const [usdRates, setUsdRates] = useState({})
  const [productCodes, setProductCodes] = useState(new Map())
  const [activeCategory, setActiveCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [highlightCleared, setHighlightCleared] = useState(false)
  const highlightActive = Boolean(highlightHsCode) && !highlightCleared
  const [updating, setUpdating] = useState(false)
  const [researchedWeights, setResearchedWeights] = useState(new Map())
  const [researchingWeights, setResearchingWeights] = useState(false)
  const [customOverrides, setCustomOverrides] = useState(new Map())
  const [editingRowSignature, setEditingRowSignature] = useState(null)
  const [editDraft, setEditDraft] = useState({ price: '', weight: '' })
  const [savingOverride, setSavingOverride] = useState(false)

  const loadSources = () =>
    fetchCustomSourceProducts().then((rows) => {
      const mine = rows.filter((row) => row.country_name.trim().toLowerCase() === countryName.trim().toLowerCase())
      setSources(mine)
      setSyncBySource((prev) =>
        Object.fromEntries(
          mine.map((source) => [source.source_id, prev[source.source_id]?.status === 'stale' ? prev[source.source_id] : {
            status: 'fresh',
            lastSyncedAt: new Date(source.fetched_at),
            error: null,
          }]),
        ),
      )
      return mine
    })

  useEffect(() => {
    let cancelled = false
    loadSources()
      .then(() => !cancelled && setStatus('ready'))
      .catch(() => !cancelled && setStatus('error'))
    // A source that records no currency (or a bare "$") falls back to the
    // country's own official currency — same rule Market Opportunities uses.
    fetchReferenceCountries()
      .then((rows) => {
        if (cancelled) return
        const match = rows.find((row) => row.name.trim().toLowerCase() === countryName.trim().toLowerCase())
        setCountryCurrency(match?.currency_code || null)
      })
      .catch(() => {})
    fetchWeightResearch()
      .then((data) => !cancelled && setResearchedWeights(new Map(Object.entries(data.results))))
      .catch(() => {})
    fetchCustomOverrides()
      .then((data) => !cancelled && setCustomOverrides(new Map(Object.entries(data))))
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the country changes
  }, [countryName])

  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    buildProductCodeIndex()
      .then((index) => !cancelled && setProductCodes(index))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [companyId, sources])

  const products = useMemo(
    () =>
      sources.flatMap((source) =>
        source.products.map((product) => {
          const rawCurrency = (product.currency || source.currency || '').trim().toUpperCase()
          return {
            ...product,
            sourceId: source.source_id,
            sourceName: source.source_name,
            sourceLabel: displaySourceName(source.source_name),
            priceLevel: priceLevelLabel(source.analysis_type),
            currency: ISO_CURRENCY_RE.test(rawCurrency) ? rawCurrency : countryCurrency,
          }
        }),
      ),
    [sources, countryCurrency],
  )

  const currencies = useMemo(() => [...new Set(products.map((p) => p.currency).filter((c) => c && c !== 'USD'))].sort(), [products])

  useEffect(() => {
    let cancelled = false
    currencies.forEach((code) =>
      fetchExchangeRate(code, 'USD')
        .then(({ rate }) => !cancelled && setUsdRates((prev) => ({ ...prev, [code]: rate })))
        .catch(() => {}),
    )
    return () => {
      cancelled = true
    }
  }, [currencies])

  const categoryCounts = useMemo(() => {
    const counts = new Map()
    products.forEach((product) => counts.set(product.category, (counts.get(product.category) ?? 0) + 1))
    return counts
  }, [products])
  const categories = useMemo(() => [...categoryCounts.keys()].sort(), [categoryCounts])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return products
      .filter((row) => activeCategory === 'all' || row.category === activeCategory)
      .filter((row) => !needle || row.name.toLowerCase().includes(needle) || row.category.toLowerCase().includes(needle))
      .filter((row) => {
        if (!highlightActive) return true
        const code = productCodes.get(row.name.toLowerCase())
        return code && code.slice(2).startsWith(highlightHsCode)
      })
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [products, activeCategory, search, highlightActive, highlightHsCode, productCodes])

  // Official conversion, then an AI-researched weight, then a custom override
  // on top — the same order the Colombia/USA tables apply (unitConversion.js).
  const resolvePerKg = (row) => {
    const basePerKg = genericPricePerKg(row.price, row.unit, row.name)
    const officialComment = explainGenericConversion(row.unit, row.name)
    const item = genericWeightResearchItem(countryName, row.sourceName, row.name, row.unit)
    const afterResearch = applyResearchedWeight(row.price, basePerKg, officialComment, item.signature, researchedWeights)
    const signature = rowSignature(row)
    const override = customOverrides.get(signature)
    return { ...applyCustomOverride(row.price, afterResearch, override), rowSignature: signature, override }
  }

  const commentFor = (row, resolved) => {
    const parts = [resolved.comment]
    if (row.low != null && row.high != null) {
      const markets = row.markets ? ` across ${row.markets} ${row.markets === 1 ? 'market' : 'markets'}` : ''
      parts.push(`Quoted range ${row.low.toLocaleString('en-US')}–${row.high.toLocaleString('en-US')}${markets}.`)
    }
    if (row.as_of) parts.push(`As of ${row.as_of}.`)
    return parts.filter(Boolean).join(' ')
  }

  const missingWeightItems = useMemo(() => {
    const bySignature = new Map()
    products.forEach((row) => {
      if (genericPricePerKg(row.price, row.unit, row.name) !== null) return
      const item = genericWeightResearchItem(countryName, row.sourceName, row.name, row.unit)
      if (!researchedWeights.has(item.signature)) bySignature.set(item.signature, item)
    })
    return [...bySignature.values()]
  }, [products, researchedWeights, countryName])

  const stats = useMemo(() => {
    let withKg = 0
    filtered.forEach((row) => {
      if (resolvePerKg(row).perKg !== null) withKg += 1
    })
    return { total: filtered.length, withKg, withoutKg: filtered.length - withKg }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolvePerKg reads only the state listed here
  }, [filtered, researchedWeights, customOverrides])

  const handleResearchWeights = async () => {
    if (researchingWeights || !missingWeightItems.length) return
    setResearchingWeights(true)
    try {
      const data = await researchMissingWeights(missingWeightItems)
      setResearchedWeights(new Map(Object.entries(data.results)))
    } catch (error) {
      window.alert(`Weight research failed: ${error.message}`)
    } finally {
      setResearchingWeights(false)
    }
  }

  // Re-reads every one of this country's sources that has a web address; a
  // source that only has a loaded file is marked stale with the reason.
  const handleUpdate = async () => {
    if (updating) return
    setUpdating(true)
    setSyncBySource((prev) => Object.fromEntries(sources.map((s) => [s.source_id, { ...prev[s.source_id], status: 'loading' }])))
    const results = await Promise.allSettled(sources.map((s) => refreshProductSource(s.source_id)))
    const failures = Object.fromEntries(
      results.map((result, i) => [
        sources[i].source_id,
        result.status === 'rejected' ? result.reason.message : result.value.status !== 'ok' ? result.value.status_message : null,
      ]),
    )
    try {
      const mine = await loadSources()
      setSyncBySource(
        Object.fromEntries(
          mine.map((source) => [
            source.source_id,
            failures[source.source_id]
              ? { status: 'stale', lastSyncedAt: new Date(source.fetched_at), error: failures[source.source_id] }
              : { status: 'fresh', lastSyncedAt: new Date(source.fetched_at), error: null },
          ]),
        ),
      )
    } finally {
      setUpdating(false)
    }
  }

  const handleStartOverrideEdit = (resolved) => {
    setEditingRowSignature(resolved.rowSignature)
    setEditDraft({
      price: resolved.override?.custom_price != null ? String(resolved.override.custom_price) : '',
      weight: resolved.override?.custom_weight_kg != null ? String(resolved.override.custom_weight_kg) : '',
    })
  }

  const handleCancelOverrideEdit = () => {
    setEditingRowSignature(null)
    setEditDraft({ price: '', weight: '' })
  }

  const handleSaveOverrideEdit = async () => {
    if (!editingRowSignature || savingOverride) return
    const customPrice = editDraft.price.trim() ? Number(editDraft.price) : null
    const customWeightKg = editDraft.weight.trim() ? Number(editDraft.weight) : null
    if ((editDraft.price.trim() && Number.isNaN(customPrice)) || (editDraft.weight.trim() && Number.isNaN(customWeightKg))) {
      window.alert('Custom price and custom weight must be numbers.')
      return
    }
    setSavingOverride(true)
    try {
      if (customPrice === null && customWeightKg === null) {
        await clearCustomOverride(editingRowSignature)
        setCustomOverrides((prev) => {
          const next = new Map(prev)
          next.delete(editingRowSignature)
          return next
        })
      } else {
        const saved = await saveCustomOverride(editingRowSignature, { customPrice, customWeightKg })
        setCustomOverrides((prev) => new Map(prev).set(editingRowSignature, saved))
      }
      handleCancelOverrideEdit()
    } catch (error) {
      window.alert(`Could not save the custom value(s): ${error.message}`)
    } finally {
      setSavingOverride(false)
    }
  }

  const handleClearOverride = async (signature) => {
    if (savingOverride) return
    setSavingOverride(true)
    try {
      await clearCustomOverride(signature)
      setCustomOverrides((prev) => {
        const next = new Map(prev)
        next.delete(signature)
        return next
      })
    } catch (error) {
      window.alert(`Could not clear the custom value(s): ${error.message}`)
    } finally {
      setSavingOverride(false)
    }
  }

  const handleExportCsv = () => {
    const headers = ['Code', 'Category', 'Product', 'Unit', 'Source', 'Currency', 'Price per Unit', 'Price per kg (local)', 'Price per kg (USD)', 'Comments']
    const csvRows = filtered.map((row) => {
      const resolved = resolvePerKg(row)
      const rate = row.currency === 'USD' ? 1 : usdRates[row.currency]
      return [
        productCodes.get(row.name.toLowerCase()) || '',
        row.category,
        row.name,
        row.unit,
        `${row.sourceName} (${row.priceLevel})`,
        row.currency || '',
        row.price,
        resolved.perKg ?? '',
        resolved.perKg !== null && rate ? (resolved.perKg * rate).toFixed(2) : '',
        commentFor(row, resolved),
      ]
    })
    downloadCsv(`${countryName.toLowerCase().replace(/\s+/g, '-')}-products.csv`, headers, csvRows)
  }

  if (status === 'loading') return <p className="price-comparison__status">Loading sources…</p>
  if (status === 'error') return <p className="price-comparison__status">Could not load the added sources.</p>
  if (sources.length === 0) {
    return showEmptyHint ? (
      <p className="price-comparison__status">
        Product analysis is not yet available for {countryName}. Add a source in Settings → Product analysis sources — a website to
        analyse, or a products file to load.
      </p>
    ) : null
  }

  return (
    <div className="price-comparison">
      <div className="price-comparison__header">
        <div>
          <h4>{showEmptyHint ? `${countryName} Product Analysis` : `${countryName} — Added Sources`}</h4>
          <p>
            {sources.map((source) => `${displaySourceName(source.source_name)} (${priceLevelLabel(source.analysis_type)})`).join(' · ')} — prices as each source
            quotes them, converted to per kg where the unit allows.
          </p>
        </div>
        <div className="price-comparison__header-actions">
          <button type="button" className="price-comparison__export-btn" onClick={handleExportCsv} disabled={!filtered.length}>
            Export CSV
          </button>
          {missingWeightItems.length > 0 && (
            <button
              type="button"
              className="price-comparison__research-btn"
              onClick={handleResearchWeights}
              disabled={researchingWeights}
              title="Ask AI to research the standard pack weight for products with no price-per-kg figure yet"
            >
              {researchingWeights ? 'Researching…' : `Research Missing Weights (${missingWeightItems.length})`}
            </button>
          )}
          <button type="button" className="price-comparison__update-btn" onClick={handleUpdate} disabled={updating}>
            {updating ? 'Updating…' : 'Update'}
          </button>
        </div>
      </div>

      <div className="price-comparison__sources">
        {sources.map((source) => (
          <SourceStatus
            key={source.source_id}
            label={`${displaySourceName(source.source_name)} (${priceLevelLabel(source.analysis_type)})`}
            sync={syncBySource[source.source_id] || { status: 'never' }}
          />
        ))}
      </div>

      {currencies.length > 0 && (
        <div className="price-comparison__rate-label">
          {currencies.map((code, index) => (
            <span key={code}>
              {index > 0 && ' · '}
              {typeof usdRates[code] === 'number' ? (
                <span className="price-comparison__rate-value">{formatOneUsdEquals(usdRates[code], code)}</span>
              ) : (
                <span className="price-comparison__rate-stale">{code}: rate unavailable — showing {code} only</span>
              )}
            </span>
          ))}
        </div>
      )}

      {highlightActive && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 12px',
            borderRadius: '8px',
            border: '1px solid rgba(53, 211, 153, 0.35)',
            background: 'rgba(53, 211, 153, 0.1)',
            color: '#6ee7b7',
            fontSize: '0.82rem',
          }}
        >
          Showing products classified under HS code {highlightHsCode} (from Available Categories).
          <button
            type="button"
            onClick={() => setHighlightCleared(true)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}
          >
            Clear filter
          </button>
        </div>
      )}

      <div className="price-comparison__chips">
        <button type="button" className={`price-comparison__chip ${activeCategory === 'all' ? 'is-active' : ''}`} onClick={() => setActiveCategory('all')}>
          All <span className="price-comparison__chip-count">{products.length}</span>
        </button>
        {categories.map((category) => (
          <button
            key={category}
            type="button"
            className={`price-comparison__chip ${activeCategory === category ? 'is-active' : ''}`}
            onClick={() => setActiveCategory(category)}
          >
            {category} <span className="price-comparison__chip-count">{categoryCounts.get(category) ?? 0}</span>
          </button>
        ))}
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search products…"
          style={{ marginLeft: 'auto', minWidth: '12rem' }}
        />
      </div>

      <div className="price-comparison__stats">
        <div className="price-comparison__stat">
          <div className="price-comparison__stat-label">Products shown</div>
          <div className="price-comparison__stat-value">{stats.total}</div>
        </div>
        <div className="price-comparison__stat">
          <div className="price-comparison__stat-label">Sources</div>
          <div className="price-comparison__stat-value">{sources.length}</div>
        </div>
        <div className="price-comparison__stat">
          <div className="price-comparison__stat-label">With price per kg</div>
          <div className="price-comparison__stat-value">{stats.withKg}</div>
        </div>
        <div className="price-comparison__stat price-comparison__stat--flag">
          <div className="price-comparison__stat-label">No price per kg</div>
          <div className="price-comparison__stat-value">{stats.withoutKg}</div>
        </div>
      </div>

      <div className={`price-comparison__table-wrap ${updating ? 'is-updating' : ''}`}>
        {updating && <div className="price-comparison__table-overlay">Fetching latest prices…</div>}
        <table className="price-comparison__table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Category</th>
              <th>Product</th>
              <th>Unit</th>
              <th>Source</th>
              <th className="num">Price per Unit</th>
              <th className="num">Price per kg</th>
              <th className="num">Reference Price (per kg)</th>
              <th>Comments</th>
              <th>Actions</th>
              <th className="num">Custom Unit (kg)</th>
              <th className="num">Custom Price</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, index) => {
              const resolved = resolvePerKg(row)
              const isEditing = editingRowSignature === resolved.rowSignature
              return (
                <tr key={`${row.sourceId}-${row.category}-${row.id}-${index}`}>
                  <td className="price-comparison__code-cell">{productCodes.get(row.name.toLowerCase()) || '—'}</td>
                  <td className="price-comparison__category-cell">{row.category}</td>
                  <td>
                    <div className="price-comparison__product-name">{row.name}</div>
                  </td>
                  <td className="price-comparison__unit-cell">{row.unit || '—'}</td>
                  <td className="price-comparison__source-cell" title={row.sourceName} style={{ overflowWrap: 'anywhere' }}>
                    {row.sourceLabel} <span style={{ opacity: 0.7 }}>({row.priceLevel})</span>
                  </td>
                  <td className="num price-comparison__price-cell">{priceLine(row.price, row.currency, usdRates)}</td>
                  <td className="num price-comparison__price-cell">
                    {resolved.perKg !== null ? (
                      <>
                        {priceLine(resolved.perKg, row.currency, usdRates)}
                        {resolved.custom && <span className="price-comparison__custom-badge">Custom</span>}
                        {!resolved.custom && resolved.researched && (
                          <span
                            className="price-comparison__researched-badge"
                            title={`AI-researched pack weight.${resolved.note ? ` ${resolved.note}` : ''}${
                              resolved.sources?.length ? ` Sources: ${resolved.sources.join(', ')}` : ''
                            }`}
                          >
                            AI
                          </span>
                        )}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="num">{resolved.perKg !== null ? priceLine(resolved.perKg, row.currency, usdRates) : '—'}</td>
                  <td className="price-comparison__comments-cell">{commentFor(row, resolved)}</td>
                  <td className="price-comparison__actions-cell">
                    {isEditing ? (
                      <div className="price-comparison__override-actions">
                        <button type="button" onClick={handleSaveOverrideEdit} disabled={savingOverride}>
                          {savingOverride ? 'Saving…' : 'Save'}
                        </button>
                        <button type="button" onClick={handleCancelOverrideEdit} disabled={savingOverride}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="price-comparison__override-actions">
                        <button
                          type="button"
                          className="price-comparison__edit-btn"
                          onClick={() => handleStartOverrideEdit(resolved)}
                          title="Edit custom price/weight"
                        >
                          ✏️
                        </button>
                        {resolved.override && (
                          <button
                            type="button"
                            className="price-comparison__clear-btn"
                            onClick={() => handleClearOverride(resolved.rowSignature)}
                            title="Clear custom value"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="num price-comparison__custom-cell">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        className="price-comparison__custom-input"
                        placeholder="kg"
                        value={editDraft.weight}
                        onChange={(event) => setEditDraft((prev) => ({ ...prev, weight: event.target.value }))}
                        disabled={savingOverride}
                        autoFocus
                      />
                    ) : (
                      (resolved.override?.custom_weight_kg ?? '—')
                    )}
                  </td>
                  <td className="num price-comparison__custom-cell">
                    {isEditing ? (
                      <input
                        type="number"
                        step="any"
                        className="price-comparison__custom-input"
                        placeholder={row.currency || 'price'}
                        value={editDraft.price}
                        onChange={(event) => setEditDraft((prev) => ({ ...prev, price: event.target.value }))}
                        disabled={savingOverride}
                      />
                    ) : (
                      (resolved.override?.custom_price ?? '—')
                    )}
                  </td>
                </tr>
              )
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={12} className="price-comparison__status">
                  No products match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default CustomSourceProductsView
