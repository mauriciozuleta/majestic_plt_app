import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { USA_SOURCES, fetchUsaSourceProducts, fetchUsaSourcingSnapshot } from './usaSourcingFetchers'
import { exportUsaSourcingToCsv, exportUsaSourcingToPdf } from './usaSourcingExport'
import { formatPriceLine } from './priceFormat'
import {
  applyCustomOverride,
  applyResearchedWeight,
  explainUsaConversion,
  usaPricePerKg,
  usaRowSignature,
  usaWeightResearchItem,
} from './unitConversion'
import { fetchCommercialCountries } from '../../../../../services/commercialStructure'
import { buildProductCodeIndex } from '../../../../../services/productPortfolio'
import { fetchWeightResearch, researchMissingWeights } from '../../../../../services/weightResearch'
import { clearCustomOverride, fetchCustomOverrides, saveCustomOverride } from '../../../../../services/productOverrides'
import './USASourcingView.css'

const SNAPSHOT_KEY_TO_SOURCE = {
  usa_beef: 'beef',
  usa_pork: 'pork',
  usa_poultry: 'poultry',
  usa_eggs: 'eggs',
  usa_grains: 'grains',
  usa_produce_fl: 'produce_fl',
  usa_produce_ca: 'produce_ca',
}

const INITIAL_SYNC_STATE = { status: 'never', lastSyncedAt: null, error: null }

// Each USDA AMS report maps 1:1 to a category today, so the "source" a
// product's price came from reads as "USDA AMS <category>" — parallel to
// Colombia's "La Mayorista" / "Corabastos", just with a single entry here
// since no USA product is currently priced by more than one report.
function sourceLabelFor(category) {
  const match = USA_SOURCES.find((s) => s.label === category)
  return `USDA AMS ${match ? match.label : category}`
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
  const badgeText =
    sync.status === 'loading' ? 'Updating…' : sync.status === 'fresh' ? 'Fresh' : sync.status === 'stale' ? 'Stale' : 'Not loaded'
  const staleTooltip =
    sync.status === 'stale' && sync.error ? `${sync.error} Showing the last successfully fetched data for this source.` : undefined

  return (
    <div className="usa-sourcing__source-status">
      <span className="usa-sourcing__source-name">{label}</span>
      <span className={`usa-sourcing__status-badge ${badgeClass}`} title={staleTooltip}>
        {badgeText}
      </span>
      {sync.lastSyncedAt && <span className="usa-sourcing__synced-at">Synced {timeLabel(sync.lastSyncedAt)}</span>}
    </div>
  )
}

function USASourcingView() {
  const { companyId } = useParams()
  const [activeCategory, setActiveCategory] = useState('all')
  const [productsBySource, setProductsBySource] = useState(() => Object.fromEntries(USA_SOURCES.map((s) => [s.key, []])))
  const [syncBySource, setSyncBySource] = useState(() => Object.fromEntries(USA_SOURCES.map((s) => [s.key, INITIAL_SYNC_STATE])))
  const [updating, setUpdating] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const [productCodes, setProductCodes] = useState(new Map())
  const [researchedWeights, setResearchedWeights] = useState(new Map())
  const [researchingWeights, setResearchingWeights] = useState(false)
  const [customOverrides, setCustomOverrides] = useState(new Map())
  const [editingRowSignature, setEditingRowSignature] = useState(null)
  const [editDraft, setEditDraft] = useState({ price: '', weight: '' })
  const [savingOverride, setSavingOverride] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchWeightResearch()
      .then((data) => {
        if (cancelled) return
        setResearchedWeights(new Map(Object.entries(data.results)))
      })
      .catch(() => {
        // Non-fatal: rows just keep showing '—' for whatever isn't researched yet.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchCustomOverrides()
      .then((data) => {
        if (cancelled) return
        setCustomOverrides(new Map(Object.entries(data)))
      })
      .catch(() => {
        // Non-fatal: rows just fall back to their automatic value.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchUsaSourcingSnapshot()
      .then((snapshots) => {
        if (cancelled) return
        setProductsBySource((prev) => {
          const next = { ...prev }
          snapshots.forEach((snapshot) => {
            const key = SNAPSHOT_KEY_TO_SOURCE[snapshot.source]
            if (key) next[key] = snapshot.products
          })
          return next
        })
        setSyncBySource((prev) => {
          const next = { ...prev }
          snapshots.forEach((snapshot) => {
            const key = SNAPSHOT_KEY_TO_SOURCE[snapshot.source]
            if (key) next[key] = { status: 'fresh', lastSyncedAt: new Date(snapshot.fetched_at), error: null }
          })
          return next
        })
      })
      .catch(() => {
        // Non-fatal: falls back to the empty "click Update" state.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    fetchCommercialCountries(companyId)
      .then((countries) => {
        const countryCodeByName = new Map(countries.map((c) => [c.name.toLowerCase(), c.country_code]))
        return buildProductCodeIndex(countryCodeByName)
      })
      .then((index) => {
        if (!cancelled) setProductCodes(index)
      })
      .catch(() => {
        // Non-fatal: the table still works without the reference codes.
      })
    return () => {
      cancelled = true
    }
  }, [companyId, productsBySource])

  const products = useMemo(() => USA_SOURCES.flatMap((s) => productsBySource[s.key] ?? []), [productsBySource])

  const categoryCounts = useMemo(() => {
    const counts = new Map()
    products.forEach((product) => counts.set(product.category, (counts.get(product.category) ?? 0) + 1))
    return counts
  }, [products])

  const categories = useMemo(() => {
    const seen = new Set(products.map((p) => p.category))
    const list = Array.from(seen).sort()
    if (!list.includes('Seafood (Gulf, domestic landings)')) list.push('Seafood (Gulf, domestic landings)')
    return list
  }, [products])

  const filtered = useMemo(() => {
    const scoped = activeCategory === 'all' ? products : products.filter((product) => product.category === activeCategory)
    return [...scoped].sort((a, b) => a.product_en.localeCompare(b.product_en))
  }, [products, activeCategory])

  const isSeafoodSelected = activeCategory === 'Seafood (Gulf, domestic landings)'

  // Resolves a product's final, effective $/kg — official conversion, then
  // an AI-researched fallback, then any custom user override on top (see
  // unitConversion.js) — plus the plain-language comment explaining
  // however it was actually produced, for the Comments column.
  const resolvePerKg = (product) => {
    const basePerKg = usaPricePerKg(product)
    const officialComment = explainUsaConversion(product)
    const item = usaWeightResearchItem(product)
    const afterResearch = applyResearchedWeight(product.price, basePerKg, officialComment, item?.signature ?? null, researchedWeights)
    const rowSignature = usaRowSignature(product)
    const override = customOverrides.get(rowSignature)
    const resolved = applyCustomOverride(product.price, afterResearch, override)
    return { ...resolved, rowSignature, override }
  }

  // Every currently-loaded product with no $/kg figure yet and no pending
  // research result — deduped by signature, since every size grade of the
  // same carton (32s, 36s, ...) shares one signature (see unitConversion.js).
  const missingWeightItems = useMemo(() => {
    const itemsBySignature = new Map()
    products.forEach((product) => {
      if (usaPricePerKg(product) !== null) return
      const item = usaWeightResearchItem(product)
      if (item && !researchedWeights.has(item.signature)) itemsBySignature.set(item.signature, item)
    })
    return Array.from(itemsBySignature.values())
  }, [products, researchedWeights])

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
      setEditingRowSignature(null)
      setEditDraft({ price: '', weight: '' })
    } catch (error) {
      window.alert(`Could not save the custom value(s): ${error.message}`)
    } finally {
      setSavingOverride(false)
    }
  }

  const handleClearOverride = async (rowSignature) => {
    if (savingOverride) return
    setSavingOverride(true)
    try {
      await clearCustomOverride(rowSignature)
      setCustomOverrides((prev) => {
        const next = new Map(prev)
        next.delete(rowSignature)
        return next
      })
    } catch (error) {
      window.alert(`Could not clear the custom value(s): ${error.message}`)
    } finally {
      setSavingOverride(false)
    }
  }

  const handleUpdate = async () => {
    if (updating) return
    setUpdating(true)
    setSyncBySource((prev) => Object.fromEntries(USA_SOURCES.map((s) => [s.key, { ...prev[s.key], status: 'loading' }])))

    const results = await Promise.allSettled(USA_SOURCES.map((s) => fetchUsaSourceProducts(s.key)))

    setProductsBySource((prev) => {
      const next = { ...prev }
      results.forEach((result, i) => {
        if (result.status === 'fulfilled') next[USA_SOURCES[i].key] = result.value
      })
      return next
    })
    setSyncBySource((prev) => {
      const next = { ...prev }
      results.forEach((result, i) => {
        const key = USA_SOURCES[i].key
        if (result.status === 'fulfilled') {
          next[key] = { status: 'fresh', lastSyncedAt: new Date(), error: null }
        } else {
          next[key] = { status: 'stale', lastSyncedAt: prev[key].lastSyncedAt, error: result.reason.message }
        }
      })
      return next
    })
    setUpdating(false)
  }

  const buildExportRows = () =>
    filtered.map((product) => ({
      category: product.category,
      productEn: product.product_en,
      price: product.price,
      pricePerKg: resolvePerKg(product).perKg,
      unit: product.unit,
      sourceDate: product.source_date,
      qualityNote: product.quality_note,
      report: product.report,
    }))

  const handleExportCsv = () => {
    exportUsaSourcingToCsv(buildExportRows(), `usa-sourcing-${activeCategory === 'all' ? 'all' : activeCategory}.csv`)
  }

  const handleExportPdf = async () => {
    if (exportingPdf) return
    setExportingPdf(true)
    try {
      await exportUsaSourcingToPdf(
        buildExportRows(),
        { generatedAt: new Date().toLocaleString() },
        `usa-sourcing-${activeCategory === 'all' ? 'all' : activeCategory}.pdf`,
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingPdf(false)
    }
  }

  const neverLoaded = USA_SOURCES.every((s) => syncBySource[s.key].status === 'never')

  return (
    <div className="usa-sourcing">
      <div className="usa-sourcing__header">
        <div>
          <h4>USA Sourcing</h4>
          <p>USDA AMS export/domestic wholesale prices — Beef, Pork, Poultry, Eggs, Grains, and shipping-point Produce.</p>
        </div>
        <div className="usa-sourcing__header-actions">
          <button type="button" className="usa-sourcing__export-btn" onClick={handleExportCsv} disabled={!filtered.length}>
            Export CSV
          </button>
          <button type="button" className="usa-sourcing__export-btn" onClick={handleExportPdf} disabled={!filtered.length || exportingPdf}>
            {exportingPdf ? 'Exporting…' : 'Export PDF'}
          </button>
          {missingWeightItems.length > 0 && (
            <button
              type="button"
              className="usa-sourcing__research-btn"
              onClick={handleResearchWeights}
              disabled={researchingWeights}
              title="Ask AI to research the standard pack weight for products with no price-per-kg figure yet"
            >
              {researchingWeights ? 'Researching…' : `Research Missing Weights (${missingWeightItems.length})`}
            </button>
          )}
          <button type="button" className="usa-sourcing__update-btn" onClick={handleUpdate} disabled={updating}>
            {updating ? 'Updating…' : 'Update'}
          </button>
        </div>
      </div>

      <div className="usa-sourcing__sources">
        {USA_SOURCES.map((s) => (
          <SourceStatus key={s.key} label={s.label} sync={syncBySource[s.key]} />
        ))}
      </div>

      {neverLoaded ? (
        <div className="usa-sourcing__status">No prices loaded yet. Click Update to fetch current USDA AMS reports.</div>
      ) : (
        <>
          <div className="usa-sourcing__chips">
            <button
              type="button"
              className={`usa-sourcing__chip ${activeCategory === 'all' ? 'is-active' : ''}`}
              onClick={() => setActiveCategory('all')}
            >
              All <span className="usa-sourcing__chip-count">{products.length}</span>
            </button>
            {categories.map((category) => (
              <button
                key={category}
                type="button"
                className={`usa-sourcing__chip ${activeCategory === category ? 'is-active' : ''}`}
                onClick={() => setActiveCategory(category)}
              >
                {category} <span className="usa-sourcing__chip-count">{categoryCounts.get(category) ?? 0}</span>
              </button>
            ))}
          </div>

          {isSeafoodSelected ? (
            <div className="usa-sourcing__status">
              Seafood is not yet available. No confirmed, directly-fetchable primary source (NOAA Fishery Market News) was identified for
              this category — see the module spec's open items. A third-party citation exists for one data point (Gulf shrimp, ex-vessel)
              but is deliberately not wired up as a live feed.
            </div>
          ) : (
            <div className={`usa-sourcing__table-wrap ${updating ? 'is-updating' : ''}`}>
              {updating && <div className="usa-sourcing__table-overlay">Fetching latest prices…</div>}
              <table className="usa-sourcing__table">
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
                  {filtered.map((product, index) => {
                    const resolved = resolvePerKg(product)
                    const isEditing = editingRowSignature === resolved.rowSignature
                    return (
                      <tr key={`${product.category}-${product.product_en}-${index}`}>
                        <td className="usa-sourcing__code-cell">{productCodes.get(product.product_en.toLowerCase()) || '—'}</td>
                        <td className="usa-sourcing__category-cell">{product.category}</td>
                        <td className="usa-sourcing__product-name">{product.product_en}</td>
                        <td className="usa-sourcing__unit-cell">{product.unit}</td>
                        <td className="usa-sourcing__source-cell">{sourceLabelFor(product.category)}</td>
                        <td className="num usa-sourcing__price-cell">{formatPriceLine(product.price, null, null)}</td>
                        <td className="num usa-sourcing__price-cell">
                          {resolved.perKg !== null ? (
                            <>
                              {formatPriceLine(resolved.perKg, null, null)}
                              {resolved.custom && <span className="usa-sourcing__custom-badge">Custom</span>}
                              {!resolved.custom && resolved.researched && (
                                <span
                                  className="usa-sourcing__researched-badge"
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
                        <td className="num">{resolved.perKg !== null ? formatPriceLine(resolved.perKg, null, null) : '—'}</td>
                        <td className="usa-sourcing__comments-cell">{resolved.comment}</td>
                        <td className="usa-sourcing__actions-cell">
                          {isEditing ? (
                            <div className="usa-sourcing__override-actions">
                              <button type="button" onClick={handleSaveOverrideEdit} disabled={savingOverride}>
                                {savingOverride ? 'Saving…' : 'Save'}
                              </button>
                              <button type="button" onClick={handleCancelOverrideEdit} disabled={savingOverride}>
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="usa-sourcing__override-actions">
                              <button
                                type="button"
                                className="usa-sourcing__edit-btn"
                                onClick={() => handleStartOverrideEdit(resolved)}
                                title="Edit custom price/weight"
                              >
                                ✏️
                              </button>
                              {resolved.override && (
                                <button
                                  type="button"
                                  className="usa-sourcing__clear-btn"
                                  onClick={() => handleClearOverride(resolved.rowSignature)}
                                  title="Clear custom value"
                                >
                                  ×
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="num usa-sourcing__custom-cell">
                          {isEditing ? (
                            <input
                              type="number"
                              step="any"
                              className="usa-sourcing__custom-input"
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
                        <td className="num usa-sourcing__custom-cell">
                          {isEditing ? (
                            <input
                              type="number"
                              step="any"
                              className="usa-sourcing__custom-input"
                              placeholder="USD"
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
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default USASourcingView
