import { useEffect, useMemo, useState } from 'react'
import { CANONICAL_CATEGORIES } from './priceComparisonData'
import {
  confirmTranslationSuggestion,
  fetchCorabastosPrices,
  fetchLaMayoristaPrices,
  fetchPriceComparisonSnapshot,
  fetchTranslationSuggestions,
  rejectTranslationSuggestion,
  requestTranslationSuggestions,
  saveTranslationOverride,
} from './priceComparisonFetchers'
import { normalizeProductName } from './productTranslations'
import { fetchColombiaProducts } from '../../../../../services/productPortfolio'
import { exportProductsToCsv, exportProductsToPdf } from './priceComparisonExport'
import { formatOneUsdEquals, formatPriceLine } from './priceFormat'
import { colombiaRowSignature } from './unitConversion'
import { useWeightResearch } from './useWeightResearch'
import { DeleteSelectedButton, RowCheckbox, SelectAllCheckbox, useCatalogSelection } from './CatalogDeleteControls'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import HsCodeCell from '../../../../hsCodes/HsCodeCell'
import { clearCustomOverride, fetchCustomOverrides, saveCustomOverride } from '../../../../../services/productOverrides'
import { missingResearchNames, resolveFromNorm } from '../../../../../services/catalogNorm'
import './ColombiaProductAnalysisView.css'

// Both La Mayorista and Corabastos always price in Colombian pesos — a
// single COP->USD rate applies to every row, no per-product currency
// detection needed (unlike a multi-country source list).
const LOCAL_CURRENCY = 'COP'

// One row's price entries, in source order, skipping any source that has
// no price for this product — this is what lets a single product with
// only one source (e.g. "Corabastos only") still render cleanly instead
// of showing an empty second line. `perKg` is null when that source's unit
// has no safe kg conversion (see unitConversion.js) — the row still shows
// its native per-unit price either way.
function buildSourceEntries(product) {
  const entries = []
  if (product.laMayorista !== null && product.laMayorista !== undefined) {
    entries.push({
      label: 'La Mayorista',
      cop: product.laMayorista,
      perKg: product.laMayoristaPerKg,
      unit: product.laMayoristaUnit,
      unitLabel: product.laMayoristaUnitLabel,
      norm: product.laMayoristaNorm ?? null,
    })
  }
  if (product.corabastos !== null && product.corabastos !== undefined) {
    entries.push({
      label: 'Corabastos',
      cop: product.corabastos,
      perKg: product.corabastosPerKg,
      unit: product.corabastosUnit,
      unitLabel: product.corabastosUnitLabel,
      norm: product.corabastosNorm ?? null,
    })
  }
  return entries
}

// Each entry's final, effective $/kg and the comment explaining how it was produced (for the Comments column): the catalog normalization module's figure
// (backend/catalog_normalization), with any custom user override on top. `customOverrides` is empty for the export, which only needs the base figure.
function resolveEntries(product, entries, customOverrides = new Map()) {
  return entries.map((entry) => {
    const rowSignature = colombiaRowSignature(product.category, product.nameEs, entry.label)
    const override = customOverrides.get(rowSignature)
    return { ...entry, ...resolveFromNorm(entry.cop, entry.norm, override), rowSignature, override }
  })
}

// The "reference price" is the higher of the available per-kg quotes —
// the only figure that's genuinely comparable across sources (a raw
// per-unit comparison would be meaningless once sources quote in
// different native units). Null when neither source has a computable
// per-kg price, rather than falling back to a non-comparable number.
function pickReferenceEntry(entries) {
  const withKg = entries.filter((entry) => entry.perKg !== null)
  if (!withKg.length) return null
  return withKg.reduce((max, entry) => (entry.perKg > max.perKg ? entry : max), withKg[0])
}

function timeLabel(date) {
  if (!date) return null
  const datePart = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const timePart = date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return `${datePart}, ${timePart}`
}

const INITIAL_SYNC_STATE = { status: 'never', lastSyncedAt: null, error: null }

function SourceStatus({ label, sync }) {
  const badgeClass =
    sync.status === 'loading'
      ? 'is-loading'
      : sync.status === 'fresh'
        ? 'is-fresh'
        : sync.status === 'stale'
          ? 'is-stale'
          : 'is-never'
  const badgeText =
    sync.status === 'loading'
      ? 'Updating…'
      : sync.status === 'fresh'
        ? 'Fresh'
        : sync.status === 'stale'
          ? 'Stale'
          : 'Not loaded'

  const staleTooltip =
    sync.status === 'stale' && sync.error ? `${sync.error} Showing the last successfully fetched data for this source.` : undefined

  return (
    <div className="price-comparison__source-status">
      <span className="price-comparison__source-name">{label}</span>
      <span className={`price-comparison__status-badge ${badgeClass}`} title={staleTooltip}>
        {badgeText}
      </span>
      {sync.lastSyncedAt && <span className="price-comparison__synced-at">Synced {timeLabel(sync.lastSyncedAt)}</span>}
    </div>
  )
}

// `highlightHsCode` (from Available Categories' country-code links, via
// MarketAnalysisPanel) filters straight down to the product(s) whose own
// reference code (see productPortfolio.js — "CO"+hs_code) falls under this
// HS code, regardless of the category chip currently selected. The parent
// remounts this view (new key) on every new click, so a plain useState
// seeded from the prop is enough — no effect needed to react to it changing.
function ColombiaProductAnalysisView({ highlightHsCode = null }) {
  const [activeCategory, setActiveCategory] = useState('all')
  const [highlightCleared, setHighlightCleared] = useState(false)
  const highlightActive = Boolean(highlightHsCode) && !highlightCleared
  const [snapshotVersion, setSnapshotVersion] = useState(0) // bumped after an item-weight research so the converted catalogs are read again
  const weightResearch = useWeightResearch(() => setSnapshotVersion((version) => version + 1))
  const selection = useCatalogSelection()
  const [customOverrides, setCustomOverrides] = useState(new Map())
  const [editingRowSignature, setEditingRowSignature] = useState(null)
  const [editDraft, setEditDraft] = useState({ price: '', weight: '' })
  const [savingOverride, setSavingOverride] = useState(false)
  // The merged table with its English names comes from the server (backend/portfolio, normalization module); `reloadKey` asks for it again after an update or a translation edit
  const [products, setProducts] = useState([])
  const [reloadKey, setReloadKey] = useState(0)
  const reloadProducts = () => setReloadKey((key) => key + 1)
  const [laMayoristaSync, setLaMayoristaSync] = useState(INITIAL_SYNC_STATE)
  const [corabastosSync, setCorabastosSync] = useState(INITIAL_SYNC_STATE)
  const [updating, setUpdating] = useState(false)
  const [rateSync, setRateSync] = useState({ status: 'never', rate: null, error: null })
  const [openTranslationKeys, setOpenTranslationKeys] = useState(() => new Set())
  const [pendingTranslations, setPendingTranslations] = useState({})
  const [savingTranslations, setSavingTranslations] = useState(false)
  const [translationSuggestions, setTranslationSuggestions] = useState(new Map())
  const [suggestingTranslations, setSuggestingTranslations] = useState(false)
  const [resolvingSuggestionKey, setResolvingSuggestionKey] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchPriceComparisonSnapshot()
      .then((snapshots) => {
        if (cancelled) return
        snapshots.forEach((snapshot) => {
          const lastSyncedAt = new Date(snapshot.fetched_at)
          if (snapshot.source === 'la_mayorista') {
            setLaMayoristaSync({ status: 'fresh', lastSyncedAt, error: null })
          } else if (snapshot.source === 'corabastos') {
            setCorabastosSync({ status: 'fresh', lastSyncedAt, error: null })
          }
        })
      })
      .catch(() => {
        // Non-fatal: falls back to the empty "click Update" state.
      })
    return () => {
      cancelled = true
    }
  }, [snapshotVersion])

  useEffect(() => {
    let cancelled = false
    fetchColombiaProducts()
      .then((rows) => !cancelled && setProducts(rows))
      .catch(() => {
        // Non-fatal: falls back to the empty "click Update" state.
      })
    return () => {
      cancelled = true
    }
  }, [snapshotVersion, reloadKey])

  useEffect(() => {
    let cancelled = false
    // The rate isn't part of the persisted snapshot (unlike the product
    // lists) — without this, the page would show snapshot-loaded prices in
    // COP only until the user clicked Update once, which reads as "the
    // currency exchange is gone" on every fresh page load. A plain rate
    // lookup is cheap and server-cached (4h), unlike the scraping
    // pipelines, so it's safe to run automatically here.
    fetchExchangeRate(LOCAL_CURRENCY, 'USD')
      .then((data) => {
        if (cancelled) return
        setRateSync({ status: 'fresh', rate: data.rate, error: null })
      })
      .catch((error) => {
        if (cancelled) return
        setRateSync((prev) => ({ status: 'stale', rate: prev.rate, error: error.message }))
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
    fetchTranslationSuggestions()
      .then((data) => {
        if (cancelled) return
        setTranslationSuggestions(new Map(data.results.map((row) => [row.product_key, row])))
      })
      .catch(() => {
        // Non-fatal: rows just show the plain "translation needed" chip without an AI suggestion.
      })
    return () => {
      cancelled = true
    }
  }, [])

  // A row merges the product of both sources: deleting it removes it from each snapshot that has it (same id).
  const describeSelected = () =>
    products
      .filter((product) => selection.selected.has(product.id))
      .map((product) => ({
        item: [
          product.laMayorista != null ? { source: 'la_mayorista', id: product.id } : null,
          product.corabastos != null ? { source: 'corabastos', id: product.id } : null,
        ].filter(Boolean),
        label: `${product.name_en} (${product.nameEs}) — ${product.laMayorista != null && product.corabastos != null ? 'La Mayorista + Corabastos' : product.laMayorista != null ? 'La Mayorista' : 'Corabastos'}`,
      }))

  const categoryCounts = useMemo(() => {
    const counts = new Map()
    products.forEach((product) => counts.set(product.category, (counts.get(product.category) ?? 0) + 1))
    return counts
  }, [products])

  const filtered = useMemo(() => {
    const scoped = activeCategory === 'all' ? products : products.filter((product) => product.category === activeCategory)
    // Sorted by the same (translated, English) name the portfolio codes are
    // alphabetized by, so codes read in ascending order down the table.
    const sorted = [...scoped].sort((a, b) =>
      a.name_en.localeCompare(b.name_en),
    )
    if (!highlightActive) return sorted
    // A code is "CO" + the real HS code (see productPortfolio.js) — strip
    // the 2-letter country prefix and match the rest against the clicked
    // HS code as a prefix, since a 6-digit highlight should still match a
    // longer real tariff code that starts with it.
    return sorted.filter((product) => {
      const code = product.hs?.code
      return code && code.slice(2).startsWith(highlightHsCode)
    })
  }, [products, activeCategory, highlightActive, highlightHsCode])

  const stats = useMemo(
    () => ({
      total: filtered.length,
      matched: filtered.filter((product) => product.matched).length,
      cheaperLaMayorista: filtered.filter((product) => product.cheaperAt === 'la_mayorista').length,
      cheaperCorabastos: filtered.filter((product) => product.cheaperAt === 'corabastos').length,
      flagged: filtered.filter((product) => product.isOutlier).length,
    }),
    [filtered],
  )

  const handleUpdate = async () => {
    if (updating) return
    setUpdating(true)
    setLaMayoristaSync((prev) => ({ ...prev, status: 'loading' }))
    setCorabastosSync((prev) => ({ ...prev, status: 'loading' }))
    setRateSync((prev) => ({ ...prev, status: 'loading' }))

    const [laResult, coraResult, rateResult] = await Promise.allSettled([
      fetchLaMayoristaPrices(),
      fetchCorabastosPrices(),
      fetchExchangeRate(LOCAL_CURRENCY, 'USD'),
    ])

    if (laResult.status === 'fulfilled') {
      setLaMayoristaSync({ status: 'fresh', lastSyncedAt: new Date(), error: null })
    } else {
      setLaMayoristaSync((prev) => ({ status: 'stale', lastSyncedAt: prev.lastSyncedAt, error: laResult.reason.message }))
    }

    if (coraResult.status === 'fulfilled') {
      setCorabastosSync({ status: 'fresh', lastSyncedAt: new Date(), error: null })
    } else {
      setCorabastosSync((prev) => ({ status: 'stale', lastSyncedAt: prev.lastSyncedAt, error: coraResult.reason.message }))
    }

    if (rateResult.status === 'fulfilled') {
      setRateSync({ status: 'fresh', rate: rateResult.value.rate, error: null })
    } else {
      // Rate fetch failing never blocks the price tables — just fall back
      // to showing raw COP values (see the price cell rendering below).
      setRateSync((prev) => ({ status: 'stale', rate: prev.rate, error: rateResult.reason.message }))
    }

    reloadProducts()
    setUpdating(false)
  }

  // The products still waiting for the weight of one item (a price per each / per bunch), by the English name the module reads.
  const missingNames = useMemo(
    () => missingResearchNames(products.flatMap((product) => buildSourceEntries(product).map((entry) => entry.norm))),
    [products],
  )

  const handleStartOverrideEdit = (entry) => {
    setEditingRowSignature(entry.rowSignature)
    setEditDraft({
      price: entry.override?.custom_price != null ? String(entry.override.custom_price) : '',
      weight: entry.override?.custom_weight_kg != null ? String(entry.override.custom_weight_kg) : '',
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

  // Every currently-loaded product whose name misses both Tier 1 (static
  // dictionary) and Tier 2 (fuzzy match) — see productTranslations.js —
  // and doesn't already have a pending suggestion or a confirmed override,
  // deduped by translation key since the same untranslated name can recur
  // across many rows/sizes.
  const missingTranslationItems = useMemo(() => {
    const itemsByKey = new Map()
    products.forEach((product) => {
      const key = normalizeProductName(product.nameEs)
      if (translationSuggestions.has(key)) return
      if (!product.translated && !itemsByKey.has(key)) {
        itemsByKey.set(key, { product_key: key, name_es: product.nameEs })
      }
    })
    return Array.from(itemsByKey.values())
  }, [products, translationSuggestions])

  const handleRequestTranslationSuggestions = async () => {
    if (suggestingTranslations || !missingTranslationItems.length) return
    setSuggestingTranslations(true)
    try {
      const data = await requestTranslationSuggestions(missingTranslationItems)
      setTranslationSuggestions(new Map(data.results.map((row) => [row.product_key, row])))
    } catch (error) {
      window.alert(`AI translation suggestions failed: ${error.message}`)
    } finally {
      setSuggestingTranslations(false)
    }
  }

  const handleConfirmSuggestion = async (key) => {
    if (resolvingSuggestionKey) return
    setResolvingSuggestionKey(key)
    try {
      await confirmTranslationSuggestion(key)
      reloadProducts()
      setTranslationSuggestions((prev) => {
        const next = new Map(prev)
        next.delete(key)
        return next
      })
    } catch (error) {
      window.alert(`Could not confirm this translation: ${error.message}`)
    } finally {
      setResolvingSuggestionKey(null)
    }
  }

  const handleRejectSuggestion = async (key) => {
    if (resolvingSuggestionKey) return
    setResolvingSuggestionKey(key)
    try {
      await rejectTranslationSuggestion(key)
      setTranslationSuggestions((prev) => {
        const next = new Map(prev)
        next.delete(key)
        return next
      })
    } catch (error) {
      window.alert(`Could not reject this suggestion: ${error.message}`)
    } finally {
      setResolvingSuggestionKey(null)
    }
  }

  const handleStartTranslationEdit = (key) => {
    setOpenTranslationKeys((prev) => new Set(prev).add(key))
  }

  const handleCancelTranslationEdit = (key) => {
    setOpenTranslationKeys((prev) => {
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    setPendingTranslations((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const handleDraftTranslationChange = (key, value) => {
    setPendingTranslations((prev) => ({ ...prev, [key]: value }))
  }

  const pendingTranslationEntries = Object.entries(pendingTranslations).filter(([, value]) => value.trim())

  const handleSaveAllTranslations = async () => {
    if (!pendingTranslationEntries.length || savingTranslations) return
    setSavingTranslations(true)
    const results = await Promise.allSettled(
      pendingTranslationEntries.map(([key, value]) => saveTranslationOverride(key, value.trim())),
    )

    const saved = {}
    const failedKeys = []
    results.forEach((result, index) => {
      const [key, value] = pendingTranslationEntries[index]
      if (result.status === 'fulfilled') {
        saved[key] = value.trim()
      } else {
        failedKeys.push(key)
      }
    })

    if (Object.keys(saved).length) reloadProducts()
    setPendingTranslations((prev) => {
      const next = { ...prev }
      Object.keys(saved).forEach((key) => delete next[key])
      return next
    })
    setOpenTranslationKeys((prev) => {
      const next = new Set(prev)
      Object.keys(saved).forEach((key) => next.delete(key))
      return next
    })
    setSavingTranslations(false)

    if (failedKeys.length) {
      window.alert(`Could not save ${failedKeys.length} translation(s). They remain in their input for retry.`)
    }
  }

  const [exportingPdf, setExportingPdf] = useState(false)

  const buildExportRows = () =>
    filtered.map((product) => {
      const categoryMeta = CANONICAL_CATEGORIES.find((item) => item.key === product.category)
      const rate = rateSync.rate
      const [laEntry, coEntry] = ['La Mayorista', 'Corabastos'].map(
        (label) => resolveEntries(product, buildSourceEntries(product)).find((e) => e.label === label) || null,
      )
      return {
        productEn: product.name_en,
        productEs: product.nameEs,
        category: categoryMeta ? `${categoryMeta.es} / ${categoryMeta.en}` : product.category,
        unit: product.unitDisplay,
        laMayoristaCop: product.laMayorista,
        laMayoristaUsd: typeof rate === 'number' && product.laMayorista != null ? product.laMayorista * rate : null,
        laMayoristaPerKgCop: laEntry?.perKg ?? null,
        corabastosCop: product.corabastos,
        corabastosUsd: typeof rate === 'number' && product.corabastos != null ? product.corabastos * rate : null,
        corabastosPerKgCop: coEntry?.perKg ?? null,
        diffPct: product.comparable ? product.diffPct : null,
        sourceTag: product.sourceTag || 'Matched',
      }
    })

  const handleExportCsv = () => {
    exportProductsToCsv(buildExportRows(), `colombia-product-analysis-${activeCategory}.csv`)
  }

  const handleExportPdf = async () => {
    if (exportingPdf) return
    setExportingPdf(true)
    try {
      const rateLabel = typeof rateSync.rate === 'number' ? formatOneUsdEquals(rateSync.rate, LOCAL_CURRENCY) : `${LOCAL_CURRENCY} only`
      await exportProductsToPdf(
        buildExportRows(),
        { generatedAt: new Date().toLocaleString(), rateLabel },
        `colombia-product-analysis-${activeCategory}.pdf`,
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingPdf(false)
    }
  }

  const neverLoaded = laMayoristaSync.status === 'never' && corabastosSync.status === 'never'

  return (
    <div className="price-comparison">
      <div className="price-comparison__header">
        <div>
          <h4>Colombia Product Analysis</h4>
          <p>La Mayorista (Medellin) vs Corabastos (Bogota) wholesale price comparison.</p>
        </div>
        <div className="price-comparison__header-actions">
          {pendingTranslationEntries.length > 0 && (
            <button
              type="button"
              className="price-comparison__save-translations-btn"
              onClick={handleSaveAllTranslations}
              disabled={savingTranslations}
            >
              {savingTranslations ? 'Saving…' : `Save changes (${pendingTranslationEntries.length})`}
            </button>
          )}
          <button type="button" className="price-comparison__export-btn" onClick={handleExportCsv} disabled={!filtered.length}>
            Export CSV
          </button>
          <button type="button" className="price-comparison__export-btn" onClick={handleExportPdf} disabled={!filtered.length || exportingPdf}>
            {exportingPdf ? 'Exporting…' : 'Export PDF'}
          </button>
          {missingNames.length > 0 && (
            <button
              type="button"
              className="price-comparison__research-btn"
              onClick={() => weightResearch.run(missingNames)}
              disabled={weightResearch.researching}
              title="Research on the web the weight of one item of the products priced per unit, so they get a price per kg"
            >
              {weightResearch.researching ? 'Researching…' : `Research item weights (${missingNames.length})`}
            </button>
          )}
          {missingTranslationItems.length > 0 && (
            <button
              type="button"
              className="price-comparison__research-btn"
              onClick={handleRequestTranslationSuggestions}
              disabled={suggestingTranslations}
              title="Try a local translation model, then a web search, for product names the dictionary doesn't cover — every suggestion needs your review before it's used"
            >
              {suggestingTranslations ? 'Suggesting…' : `Suggest Translations (${missingTranslationItems.length})`}
            </button>
          )}
          <button type="button" className="price-comparison__update-btn" onClick={handleUpdate} disabled={updating}>
            {updating ? 'Updating…' : 'Update'}
          </button>
        </div>
      </div>

      <div className="price-comparison__sources">
        <SourceStatus label="La Mayorista" sync={laMayoristaSync} />
        <SourceStatus label="Corabastos" sync={corabastosSync} />
      </div>

      {rateSync.status !== 'never' && (
        <div className="price-comparison__rate-label">
          {typeof rateSync.rate === 'number' ? (
            <>
              <span className="price-comparison__rate-value">{formatOneUsdEquals(rateSync.rate, LOCAL_CURRENCY)}</span>
              {rateSync.status === 'stale' && <span className="price-comparison__rate-stale"> (last known rate — refresh failed)</span>}
            </>
          ) : (
            <span className="price-comparison__rate-stale">
              Live conversion unavailable{rateSync.error ? `: ${rateSync.error}` : ''} — showing {LOCAL_CURRENCY} only.
            </span>
          )}
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

      {neverLoaded ? (
        <div className="price-comparison__status">
          No prices loaded yet. Click Update to fetch current La Mayorista and Corabastos prices.
        </div>
      ) : (
        <>
          <div className="price-comparison__chips">
            <button
              type="button"
              className={`price-comparison__chip ${activeCategory === 'all' ? 'is-active' : ''}`}
              onClick={() => setActiveCategory('all')}
            >
              All <span className="price-comparison__chip-count">{products.length}</span>
            </button>
            {CANONICAL_CATEGORIES.map((category) => (
              <button
                key={category.key}
                type="button"
                className={`price-comparison__chip ${activeCategory === category.key ? 'is-active' : ''}`}
                onClick={() => setActiveCategory(category.key)}
              >
                {category.es} / {category.en} <span className="price-comparison__chip-count">{categoryCounts.get(category.key) ?? 0}</span>
              </button>
            ))}
          </div>

          <div className="price-comparison__stats">
            <div className="price-comparison__stat">
              <div className="price-comparison__stat-label">Products shown</div>
              <div className="price-comparison__stat-value">{stats.total}</div>
            </div>
            <div className="price-comparison__stat">
              <div className="price-comparison__stat-label">Matched both sources</div>
              <div className="price-comparison__stat-value">{stats.matched}</div>
            </div>
            <div className="price-comparison__stat">
              <div className="price-comparison__stat-label">Cheaper at La Mayorista</div>
              <div className="price-comparison__stat-value">{stats.cheaperLaMayorista}</div>
            </div>
            <div className="price-comparison__stat">
              <div className="price-comparison__stat-label">Cheaper at Corabastos</div>
              <div className="price-comparison__stat-value">{stats.cheaperCorabastos}</div>
            </div>
            <div className="price-comparison__stat price-comparison__stat--flag">
              <div className="price-comparison__stat-label">Flagged for review</div>
              <div className="price-comparison__stat-value">{stats.flagged}</div>
            </div>
          </div>

          <div className="catalog-select__toolbar">
            <DeleteSelectedButton
              selection={selection}
              describe={describeSelected}
              onDeleted={() => setSnapshotVersion((version) => version + 1)}
            />
          </div>

          <div className={`price-comparison__table-wrap ${updating ? 'is-updating' : ''}`}>
            {updating && <div className="price-comparison__table-overlay">Fetching latest prices…</div>}
            <table className="price-comparison__table">
              <thead>
                <tr>
                  <th className="catalog-select__col">
                <SelectAllCheckbox selection={selection} rowKeys={filtered.map((product) => product.id)} />
              </th>
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
                {filtered.map((product) => {
                  const categoryMeta = CANONICAL_CATEGORIES.find((item) => item.key === product.category)
                  const translation = { text: product.name_en, isTranslated: product.translated }
                  const translationKey = normalizeProductName(product.nameEs)
                  const isEditingTranslation = openTranslationKeys.has(translationKey)
                  const suggestion = translationSuggestions.get(translationKey)
                  const isResolvingSuggestion = resolvingSuggestionKey === translationKey
                  const sourceEntries = resolveEntries(product, buildSourceEntries(product), customOverrides)
                  const referenceEntry = pickReferenceEntry(sourceEntries)
                  return (
                    <tr key={product.id}>
                      <td className="catalog-select__col">
                        <RowCheckbox selection={selection} rowKey={product.id} label={product.nameEs} />
                      </td>
                      <td className="price-comparison__code-cell"><HsCodeCell hs={product.hs} /></td>
                      <td className="price-comparison__category-cell">
                        {categoryMeta ? `${categoryMeta.es} / ${categoryMeta.en}` : product.category}
                      </td>
                      <td>
                        <div className="price-comparison__product-name">
                          {translation.text}
                          {!translation.isTranslated && !isEditingTranslation && !suggestion && (
                            <button
                              type="button"
                              className="price-comparison__translation-needed"
                              onClick={() => handleStartTranslationEdit(translationKey)}
                            >
                              translation needed
                            </button>
                          )}
                        </div>
                        {!translation.isTranslated && !isEditingTranslation && suggestion && (
                          <div
                            className="price-comparison__suggestion"
                            title={
                              suggestion.tier === 4
                                ? 'Web-search fallback — lower confidence than the local translation model. Verify before confirming.'
                                : 'Local translation model — verify before confirming.'
                            }
                          >
                            <span className="price-comparison__suggestion-text">{suggestion.suggestion_en}</span>
                            <span className="price-comparison__suggestion-badge">
                              AI suggestion (tier {suggestion.tier}) — needs review
                            </span>
                            <button
                              type="button"
                              className="price-comparison__suggestion-confirm"
                              onClick={() => handleConfirmSuggestion(translationKey)}
                              disabled={isResolvingSuggestion}
                            >
                              {isResolvingSuggestion ? '…' : 'Confirm'}
                            </button>
                            <button
                              type="button"
                              className="price-comparison__suggestion-reject"
                              onClick={() => handleRejectSuggestion(translationKey)}
                              disabled={isResolvingSuggestion}
                            >
                              Reject
                            </button>
                            <button
                              type="button"
                              className="price-comparison__translation-needed"
                              onClick={() => handleStartTranslationEdit(translationKey)}
                            >
                              edit manually
                            </button>
                          </div>
                        )}
                        {isEditingTranslation && (
                          <div className="price-comparison__translation-editor">
                            <input
                              type="text"
                              className="price-comparison__translation-input"
                              placeholder="English name"
                              value={pendingTranslations[translationKey] || ''}
                              onChange={(event) => handleDraftTranslationChange(translationKey, event.target.value)}
                              autoFocus
                              disabled={savingTranslations}
                              onKeyDown={(event) => {
                                if (event.key === 'Escape') handleCancelTranslationEdit(translationKey)
                              }}
                            />
                            <button
                              type="button"
                              className="price-comparison__translation-cancel"
                              onClick={() => handleCancelTranslationEdit(translationKey)}
                              disabled={savingTranslations}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </td>
                      <td className="price-comparison__unit-cell">{product.unitDisplay}</td>
                      <td className="price-comparison__source-cell">
                        {sourceEntries.map((entry) => (
                          <div key={entry.label}>{entry.label}</div>
                        ))}
                      </td>
                      <td className="num price-comparison__price-cell">
                        {sourceEntries.map((entry) => (
                          <div key={entry.label}>
                            {formatPriceLine(
                              typeof rateSync.rate === 'number' ? entry.cop * rateSync.rate : null,
                              entry.cop,
                              LOCAL_CURRENCY,
                            )}
                          </div>
                        ))}
                      </td>
                      <td className="num price-comparison__price-cell">
                        {sourceEntries.map((entry) => (
                          <div key={entry.label}>
                            {entry.perKg !== null ? (
                              <>
                                {formatPriceLine(
                                  typeof rateSync.rate === 'number' ? entry.perKg * rateSync.rate : null,
                                  entry.perKg,
                                  LOCAL_CURRENCY,
                                )}
                                {entry.custom && <span className="price-comparison__custom-badge">Custom</span>}
                                {!entry.custom && entry.researched && (
                                  <span
                                    className="price-comparison__researched-badge"
                                    title={`AI-researched pack weight.${entry.note ? ` ${entry.note}` : ''}${
                                      entry.sources?.length ? ` Sources: ${entry.sources.join(', ')}` : ''
                                    }`}
                                  >
                                    AI
                                  </span>
                                )}
                                {!entry.custom && entry.reference && (
                                  <span
                                    className="price-comparison__researched-badge"
                                    title={`USDA published item weight (no AI).${entry.note ? ` ${entry.note}` : ''}`}
                                  >
                                    USDA
                                  </span>
                                )}
                              </>
                            ) : (
                              '—'
                            )}
                          </div>
                        ))}
                      </td>
                      <td className="num">
                        {referenceEntry
                          ? formatPriceLine(
                              typeof rateSync.rate === 'number' ? referenceEntry.perKg * rateSync.rate : null,
                              referenceEntry.perKg,
                              LOCAL_CURRENCY,
                            )
                          : '—'}
                      </td>
                      <td className="price-comparison__comments-cell">
                        {sourceEntries.map((entry) => (
                          <div key={entry.label}>
                            <strong>{entry.label}:</strong> {entry.comment}
                          </div>
                        ))}
                      </td>
                      <td className="price-comparison__actions-cell">
                        {sourceEntries.map((entry) =>
                          editingRowSignature === entry.rowSignature ? (
                            <div key={entry.label} className="price-comparison__override-actions">
                              <button type="button" onClick={handleSaveOverrideEdit} disabled={savingOverride}>
                                {savingOverride ? 'Saving…' : 'Save'}
                              </button>
                              <button type="button" onClick={handleCancelOverrideEdit} disabled={savingOverride}>
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div key={entry.label} className="price-comparison__override-actions">
                              <button
                                type="button"
                                className="price-comparison__edit-btn"
                                onClick={() => handleStartOverrideEdit(entry)}
                                title={`Edit custom price/weight for ${entry.label}`}
                              >
                                ✏️
                              </button>
                              {entry.override && (
                                <button
                                  type="button"
                                  className="price-comparison__clear-btn"
                                  onClick={() => handleClearOverride(entry.rowSignature)}
                                  title="Clear custom value"
                                >
                                  ×
                                </button>
                              )}
                            </div>
                          ),
                        )}
                      </td>
                      <td className="num price-comparison__custom-cell">
                        {sourceEntries.map((entry) =>
                          editingRowSignature === entry.rowSignature ? (
                            <input
                              key={entry.label}
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
                            <div key={entry.label}>{entry.override?.custom_weight_kg ?? '—'}</div>
                          ),
                        )}
                      </td>
                      <td className="num price-comparison__custom-cell">
                        {sourceEntries.map((entry) =>
                          editingRowSignature === entry.rowSignature ? (
                            <input
                              key={entry.label}
                              type="number"
                              step="any"
                              className="price-comparison__custom-input"
                              placeholder={LOCAL_CURRENCY}
                              value={editDraft.price}
                              onChange={(event) => setEditDraft((prev) => ({ ...prev, price: event.target.value }))}
                              disabled={savingOverride}
                            />
                          ) : (
                            <div key={entry.label}>{entry.override?.custom_price ?? '—'}</div>
                          ),
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default ColombiaProductAnalysisView
