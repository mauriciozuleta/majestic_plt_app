import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchMarketAnalysisRegions } from '../../services/commercialStructure'
import { fetchProductSources } from '../../services/productSources'
import {
  addToMarketOpportunityPriority,
  fetchMarketOpportunityPairs,
  fetchMarketOpportunityPriority,
  getOrComputeComparison,
  removeFromMarketOpportunityPriority,
} from '../../services/marketOpportunities'
import { fetchProductSam } from '../../services/globalTradeData'
import { formatCurrencyValue } from '../../utils/currencyFormat'

const TARGET_OPTIONS = [
  { key: 'region', label: 'By Region' },
  { key: 'country', label: 'By Country' },
]

// Sort/rating-order plumbing for the results table below.
const RATING_ORDER = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable']
const SORT_OPTIONS = [
  { key: 'rating', label: 'Opportunity Rating' },
  { key: 'diff_pct', label: 'Diff %' },
  { key: 'sam_desc', label: 'Country SAM (High to Low)' },
  { key: 'sam_asc', label: 'Country SAM (Low to High)' },
  { key: 'priority', label: 'Priority list' },
]

// A product on a comparison's priority list: its target country + name.
const priorityKey = (row) => `${row.target_country}|${row.product_name}`
const priorityItem = (sourceCountry, key) => {
  const [targetCountry, ...name] = key.split('|')
  return { source_country: sourceCountry, target_country: targetCountry, product_name: name.join('|') }
}

// Ticks not yet added to / removed from the priority list, kept per comparison
// in this browser so they survive leaving the page. Storage can be
// unavailable (private window) — the page still works without it.
const pendingStorageKey = (runKey) => `market-opportunities:priority-pending:${runKey}`
function readPending(runKey) {
  try {
    const stored = JSON.parse(window.localStorage.getItem(pendingStorageKey(runKey)) || 'null')
    return { add: new Set(stored?.add || []), remove: new Set(stored?.remove || []) }
  } catch {
    return { add: new Set(), remove: new Set() }
  }
}
function writePending(runKey, pending) {
  try {
    if (!pending.add.size && !pending.remove.size) window.localStorage.removeItem(pendingStorageKey(runKey))
    else window.localStorage.setItem(pendingStorageKey(runKey), JSON.stringify({ add: [...pending.add], remove: [...pending.remove] }))
  } catch {
    // not remembered across visits — fine
  }
}

// SAM here is product-level: UN Comtrade imports of the row's exact 6-digit
// HS code, each country at its latest reported year.
const SAM_SCOPE_NOTE = "Imports of the product's exact 6-digit HS code (UN Comtrade), each country's latest reported year."

const formatDateTime = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function ratingRank(rating) {
  const index = RATING_ORDER.indexOf(rating)
  return index === -1 ? RATING_ORDER.length : index
}

function formatOriginal(original) {
  if (!original || original.value == null) return '—'
  const amount = Number(original.value).toLocaleString('en-US', { maximumFractionDigits: 2 })
  return `${original.currency ? `${original.currency} ` : ''}${amount} / ${original.unit || '—'}`
}

function formatUsdPerKg(value) {
  return value == null ? '—' : `${formatCurrencyValue(value, 'USD')}/kg`
}

function formatDiffPct(value) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

// Whole-dollar formatting for a SAM figure — same convention SamPanel.jsx's
// own money() already uses for a region/category total (a $/kg per-product
// price needs cents to be meaningful; a multi-million-dollar market total
// never does).
function formatSam(value) {
  return value == null ? '—' : formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// `rate` is how many units of the currency equal 1 USD (see
// usd_rates.py/marketOpportunities.js's own doc-comments for the
// direction) — shown in exactly this raw, stored form so it stays
// checkable against a real-world quote by eye, rather than inverted for
// display and risking the two ever drifting apart.
function formatRateDate(row, side) {
  const date = side === 'source' ? row.exchange_rate_source_date : row.exchange_rate_target_date
  const rate = side === 'source' ? row.exchange_rate_source_used : row.exchange_rate_target_used
  if (rate == null) return null
  return `1 USD = ${rate.toFixed(4)} ${side === 'source' ? row.source_price_original.currency : row.target_price_original.currency}${date ? ` (${date})` : ''}`
}

// A row's review reasons (see backend/routers/market_opportunities.py) map
// onto this app's existing badge vocabulary (MarketAnalysisView.css) —
// never a new color, per spec — chosen by what each reason actually means:
// a curated-override match is the amber "Bilateral" treatment (a real
// match, but not from an identical name, same "real but partial/qualified"
// idea that badge already carries); anything that blocked the actual
// diff_pct computation (an unconvertible unit, no USD exchange rate, no
// currency at all) is the red "Estimated · Low Confidence" treatment,
// since it's a genuinely un-computed figure, the strongest caveat this
// app's vocabulary has; anything else that just isn't a clean exact-name
// match reuses the plain blue "Estimated" treatment.
function reviewBadges(row) {
  if (row.match_confidence !== 'review') return []
  const reasons = row.review_reasons || []
  const badges = []
  if (row.match_tier === 'curated_override') badges.push({ label: 'Curated Match', className: 'market-analysis__bilateral-badge' })
  if (row.match_tier === 'hs_code') badges.push({ label: 'HS Code Match', className: 'market-analysis__bilateral-badge' })
  if (row.match_tier === 'ai_match') badges.push({ label: 'AI Match', className: 'market-analysis__bilateral-badge' })
  if (reasons.some((r) => r.startsWith('Different price levels'))) {
    badges.push({ label: 'Wholesale vs Retail', className: 'market-analysis__estimated-badge' })
  }
  // A count-based unit converted via a Haiku-estimated pack weight
  // (countWeightConversion.js's 'cached_estimate'/'fresh_haiku_estimate')
  // — never the same treatment as an official USDA-standard egg
  // conversion, which needs no badge of its own beyond whatever the match
  // tier already earned (an official, non-estimated factor, same
  // precedent as unitConversion.js's other official conversions).
  const isAiEstimatedWeight = reasons.some((r) => /ai-estimated pack weight/i.test(r))
  if (isAiEstimatedWeight) badges.push({ label: 'Estimated Unit Weight', className: 'market-analysis__estimated-badge' })
  const blocksScore = reasons.some((r) => /could not be converted|no usd exchange rate|no currency could be determined|common usd\/kg basis/i.test(r))
  if (blocksScore) badges.push({ label: 'Unresolved', className: 'market-analysis__estimated-badge market-analysis__estimated-badge--low-confidence' })
  else if (badges.length === 0) badges.push({ label: 'Review', className: 'market-analysis__estimated-badge' })
  return badges
}

// Results: when every target country in the selection already has a saved
// comparison, that saved run is shown as-is (no recompute, no AI calls);
// otherwise — or on Recompute — runs computeMarketOpportunity()
// (src/services/marketOpportunities.js), persists the scored rows (Step 3/5
// of the spec — backend computes diff_pct/opportunity_rating/
// match_confidence) together with the target product names and the
// unmatched list, and renders a sortable/filterable table plus the separate
// "no match found in target market" list. A run is a full recompute of its
// scope, same convention the backend's own overwrite-on-save already uses.
function MarketOpportunityResults({ sourceCountry, targetCountries, isRegion, region, onSaved }) {
  const [runStatus, setRunStatus] = useState('idle')
  const [runError, setRunError] = useState(null)
  const [aiMatchErrors, setAiMatchErrors] = useState({})
  const [rows, setRows] = useState([])
  const [unmatchedByTarget, setUnmatchedByTarget] = useState({})
  const [calculatedAt, setCalculatedAt] = useState(null)
  // 'saved' when the rows were loaded from a saved run, 'computed' after a fresh run
  const [resultOrigin, setResultOrigin] = useState(null)
  // true when a saved run predates saving the unmatched list
  const [unmatchedUnknown, setUnmatchedUnknown] = useState(false)
  // { key, at } — set by the Recompute button; `at` tells a new click apart
  const [recomputeRequest, setRecomputeRequest] = useState(null)
  const handledRecomputeRef = useRef(null)
  const [sortKey, setSortKey] = useState('rating')
  const [search, setSearch] = useState('')
  const [targetFilter, setTargetFilter] = useState('')
  // Product-level SAM for the run's region: every 6-digit HS code in the
  // rows, per country and summed for the region (both Target modes only ever
  // draw from one region). Fetched once the rows are in; costs at most one
  // Comtrade call per country the first time (cached after).
  const [productSam, setProductSam] = useState({ status: 'idle', data: null, error: null })
  const hsKey = useMemo(
    () => [...new Set(rows.map((row) => row.hs_code).filter((code) => /^\d{6}$/.test(code || '')))].sort().join(','),
    [rows],
  )

  useEffect(() => {
    if (!region || !hsKey) return undefined
    let cancelled = false
    setProductSam({ status: 'loading', data: null, error: null })
    fetchProductSam(region, hsKey.split(','))
      .then((data) => !cancelled && setProductSam({ status: 'ready', data, error: null }))
      .catch((err) => !cancelled && setProductSam({ status: 'error', data: null, error: err?.message || 'Could not load SAM.' }))
    return () => {
      cancelled = true
    }
  }, [region, hsKey])
  // Which rating groups are expanded — same "starts collapsed, click to
  // open" convention as this app's other collapsible sections
  // (AvailableCategoriesPanel's HS sections, GlobalTamPanel's category
  // cards): empty Set means every group starts collapsed.
  const [expandedRatings, setExpandedRatings] = useState(() => new Set())

  const targetKey = targetCountries.join('|')
  const runKey = `${sourceCountry}>${targetKey}`

  // Priority list (saved) and the ticks not yet applied to it (this browser).
  const [priority, setPriority] = useState(() => new Set())
  const [pending, setPending] = useState(() => readPending(runKey))
  const [pendingRunKey, setPendingRunKey] = useState(runKey)
  const [priorityBusy, setPriorityBusy] = useState(false)
  const [priorityError, setPriorityError] = useState('')
  if (pendingRunKey !== runKey) {
    // Another comparison was opened: its own remembered ticks.
    setPendingRunKey(runKey)
    setPending(readPending(runKey))
  }

  useEffect(() => {
    if (!sourceCountry || targetCountries.length === 0) return undefined
    let cancelled = false
    fetchMarketOpportunityPriority(sourceCountry, targetCountries)
      .then((data) => !cancelled && setPriority(new Set(data.items.map((item) => `${item.target_country}|${item.product_name}`))))
      .catch((err) => !cancelled && setPriorityError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- targetKey is targetCountries' own stable identity
  }, [sourceCountry, targetKey])

  useEffect(() => {
    if (!sourceCountry || targetCountries.length === 0) return undefined
    let cancelled = false
    const forceRecompute = recomputeRequest?.key === runKey && recomputeRequest.at !== handledRecomputeRef.current
    handledRecomputeRef.current = recomputeRequest?.at ?? null

    setRunStatus('running')
    setRunError(null)
    getOrComputeComparison(sourceCountry, targetCountries, { force: forceRecompute })
      .then((result) => {
        // A fresh run is saved even if the selection changed meanwhile, so the
        // saved list still needs refreshing.
        if (result.origin === 'computed' && result.rows.length > 0) onSaved?.()
        if (cancelled) return
        setAiMatchErrors(result.aiMatchErrors)
        setRows(result.rows)
        setUnmatchedByTarget(result.unmatchedByTarget)
        setUnmatchedUnknown(result.unmatchedUnknown)
        setCalculatedAt(result.calculatedAt)
        setResultOrigin(result.origin)
        setRunStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setRunError(err?.message || 'Could not compute this comparison.')
        setRunStatus('error')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- targetKey is targetCountries' own stable identity
  }, [sourceCountry, targetKey, recomputeRequest])

  // SAM for this row's own 6-digit HS code, two ways: the REGION total (all
  // countries of the run's region that reported it) and the row's own TARGET
  // COUNTRY's figure. Null when the product has no 6-digit code yet, or no
  // country reported it. Defined before filteredSortedRows below (its useMemo
  // callback runs synchronously this render and would otherwise reference
  // these before they're assigned).
  const samProductFor = useCallback((row) => productSam.data?.products?.[row.hs_code] ?? null, [productSam])
  const getRegionSam = useCallback((row) => samProductFor(row)?.region_total ?? null, [samProductFor])
  const getSamValue = useCallback((row) => samProductFor(row)?.countries?.[row.target_country]?.value ?? null, [samProductFor])
  const samCountryStatus = (name) => productSam.data?.countries?.find((item) => item.name === name) ?? null
  const samTitle = (row, scope) => {
    if (productSam.status === 'loading') return 'Loading product-level SAM…'
    if (productSam.status === 'error') return productSam.error
    if (!/^\d{6}$/.test(row.hs_code || '')) return 'Product has no 6-digit HS code yet'
    const product = samProductFor(row)
    if (scope === 'region') {
      const reported = Object.entries(product?.countries || {})
      const total = productSam.data?.countries?.length ?? 0
      if (!reported.length) return `No country in ${region} reported imports of HS ${row.hs_code}`
      return `HS ${row.hs_code} imports — ${region}, ${reported.length} of ${total} countries reported: ${reported
        .map(([name, item]) => `${name} ${item.year}`)
        .join(', ')}`
    }
    const country = product?.countries?.[row.target_country]
    if (country) return `HS ${row.hs_code} imports — ${row.target_country}, ${country.year}`
    const status = samCountryStatus(row.target_country)
    if (status?.status === 'error') return `Couldn't load ${row.target_country}'s figures: ${status.error}`
    if (status?.status === 'no_product_data') return `${row.target_country} has no 6-digit trade data`
    if (status?.status === 'no_data' || status?.status === 'not_in_comtrade') return `${row.target_country} has no UN Comtrade data`
    return `${row.target_country} reported no imports of HS ${row.hs_code}${status?.year ? ` in ${status.year}` : ''}`
  }
  const formatSamCell = (value) => (productSam.status === 'loading' ? '…' : formatSam(value))
  const samProblems = (productSam.data?.countries || []).filter((item) => item.status === 'error')

  const filteredSortedRows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    let filtered = rows.filter(
      (row) =>
        !needle ||
        row.product_name.toLowerCase().includes(needle) ||
        (row._target_display_name || '').toLowerCase().includes(needle) ||
        row.target_country.toLowerCase().includes(needle),
    )
    if (targetFilter) filtered = filtered.filter((row) => row.target_country === targetFilter)
    if (sortKey === 'priority') filtered = filtered.filter((row) => priority.has(priorityKey(row)))
    const sorted = [...filtered]
    if (sortKey === 'diff_pct') {
      sorted.sort((a, b) => (a.diff_pct ?? Infinity) - (b.diff_pct ?? Infinity))
    } else if (sortKey === 'sam_desc') {
      // Unknown SAM (null) always sinks to the bottom regardless of
      // direction — never presented as if it were a real "lowest" value.
      sorted.sort((a, b) => (getSamValue(b) ?? -Infinity) - (getSamValue(a) ?? -Infinity))
    } else if (sortKey === 'sam_asc') {
      sorted.sort((a, b) => (getSamValue(a) ?? Infinity) - (getSamValue(b) ?? Infinity))
    } else {
      sorted.sort((a, b) => ratingRank(a.opportunity_rating) - ratingRank(b.opportunity_rating) || (a.diff_pct ?? Infinity) - (b.diff_pct ?? Infinity))
    }
    return sorted
  }, [rows, search, targetFilter, sortKey, getSamValue, priority])

  // Grouped by opportunity rating, in the scale's own fixed order
  // (RATING_ORDER) regardless of `sortKey` — sortKey only ever orders rows
  // WITHIN a group now (moot when sortKey is 'rating' itself, since every
  // row in a group already shares that rating; the diff_pct tie-breaker in
  // filteredSortedRows's own sort still applies). A row with no rating at
  // all (diff_pct couldn't be computed) gets its own trailing "Unrated"
  // group rather than being silently dropped from the grouping.
  const groupedRows = useMemo(() => {
    const byRating = new Map()
    filteredSortedRows.forEach((row) => {
      const key = row.opportunity_rating || 'Unrated'
      if (!byRating.has(key)) byRating.set(key, [])
      byRating.get(key).push(row)
    })
    return [...RATING_ORDER, 'Unrated'].filter((key) => byRating.has(key)).map((rating) => ({ rating, rows: byRating.get(rating) }))
  }, [filteredSortedRows])

  const toggleRating = (rating) => {
    setExpandedRatings((current) => {
      const next = new Set(current)
      if (next.has(rating)) next.delete(rating)
      else next.add(rating)
      return next
    })
  }

  const unmatchedEntries = useMemo(
    () => Object.entries(unmatchedByTarget).filter(([, list]) => list.length > 0),
    [unmatchedByTarget],
  )
  const totalUnmatched = unmatchedEntries.reduce((sum, [, list]) => sum + list.length, 0)
  // Source products found in the target market — one row each (per target
  // country); a run saved before that rule may still have several.
  const matchedProductCount = useMemo(() => new Set(rows.map((row) => `${row.target_country}|${row.product_name}`)).size, [rows])

  // Same "collapsed by default, click to open" treatment as the rating
  // groups above — grouped by target country, its own natural key (a
  // By Country run only ever has one group, but it still gets the same
  // collapsible treatment for consistency rather than a special case).
  const [expandedUnmatched, setExpandedUnmatched] = useState(() => new Set())
  const toggleUnmatched = (targetCountry) => {
    setExpandedUnmatched((current) => {
      const next = new Set(current)
      if (next.has(targetCountry)) next.delete(targetCountry)
      else next.add(targetCountry)
      return next
    })
  }

  const recompute = () => setRecomputeRequest({ key: runKey, at: Date.now() })

  // A row is ticked when it's on the priority list (unless being removed) or
  // ticked to be added. Only products in this comparison count toward the buttons.
  const rowKeys = new Set(rows.map(priorityKey))
  const toAdd = [...pending.add].filter((key) => rowKeys.has(key) && !priority.has(key))
  const toRemove = [...pending.remove].filter((key) => priority.has(key))
  const isTicked = (key) => (priority.has(key) && !pending.remove.has(key)) || pending.add.has(key)
  const updatePending = (next) => {
    setPending(next)
    writePending(runKey, next)
  }
  const togglePriority = (row) => {
    const key = priorityKey(row)
    const add = new Set(pending.add)
    const remove = new Set(pending.remove)
    if (priority.has(key)) {
      if (remove.has(key)) remove.delete(key)
      else remove.add(key)
    } else if (add.has(key)) add.delete(key)
    else add.add(key)
    updatePending({ add, remove })
  }
  const applyPriority = async (keys, action) => {
    setPriorityBusy(true)
    setPriorityError('')
    try {
      const items = keys.map((key) => priorityItem(sourceCountry, key))
      if (action === 'add') await addToMarketOpportunityPriority(items)
      else await removeFromMarketOpportunityPriority(items)
      const nextPriority = new Set(priority)
      keys.forEach((key) => (action === 'add' ? nextPriority.add(key) : nextPriority.delete(key)))
      setPriority(nextPriority)
      const add = new Set(pending.add)
      const remove = new Set(pending.remove)
      keys.forEach((key) => (action === 'add' ? add.delete(key) : remove.delete(key)))
      updatePending({ add, remove })
    } catch (err) {
      setPriorityError(err.message)
    } finally {
      setPriorityBusy(false)
    }
  }
  const priorityCount = [...priority].filter((key) => rowKeys.has(key)).length

  if (runStatus === 'idle' || runStatus === 'running') {
    return <p className="market-analysis__hint">Comparing {sourceCountry}'s prices against {targetCountries.length > 1 ? `${targetCountries.length} countries` : targetCountries[0]}…</p>
  }
  if (runStatus === 'error') return <p className="market-analysis__hint">{runError}</p>

  return (
    <div className="market-opportunities__results">
      <div className="market-opportunities__run-info">
        <p className="market-analysis__hint">
          {matchedProductCount} {sourceCountry} product{matchedProductCount === 1 ? '' : 's'} found in the target market
          {rows.length !== matchedProductCount && ` (${rows.length} rows — recompute for one row per product)`},{' '}
          {unmatchedUnknown ? 'unmatched products not saved with this run' : `${totalUnmatched} with no match found in the target market`}.{' '}
          {calculatedAt && (resultOrigin === 'saved' ? `Saved comparison, computed ${formatDateTime(calculatedAt)}.` : `Last computed: ${formatDateTime(calculatedAt)}.`)}
        </p>
        <button type="button" className="market-opportunities__recompute" onClick={recompute}>
          Recompute
        </button>
      </div>
      {productSam.status === 'error' && <p className="market-analysis__hint">Product-level SAM didn't load ({productSam.error}).</p>}
      {samProblems.length > 0 && (
        <p className="market-analysis__hint">
          Product-level SAM is missing {samProblems.map((item) => `${item.name} (${item.error})`).join(', ')} — the region totals leave
          {samProblems.length === 1 ? ' it' : ' them'} out.
        </p>
      )}
      {Object.entries(aiMatchErrors).map(([country, message]) => (
        <p key={country} className="market-analysis__hint">
          AI matching for {country} didn't complete ({message}) — products it couldn't judge are paired by shared HS code only.
        </p>
      ))}

      {rows.length > 0 && (
        <>
          <div className="global-tam__controls">
            <label className="available-categories__search">
              Search
              <input type="text" value={search} placeholder="Search product or target country…" onChange={(event) => setSearch(event.target.value)} />
            </label>
            <label className="global-tam__sort">
              Sort by
              <select value={sortKey} onChange={(event) => setSortKey(event.target.value)}>
                {SORT_OPTIONS.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="market-opportunities__priority-actions">
              <button
                type="button"
                className="market-opportunities__recompute market-opportunities__priority-add"
                onClick={() => applyPriority(toAdd, 'add')}
                disabled={!toAdd.length || priorityBusy}
              >
                Add to priority list{toAdd.length ? ` (${toAdd.length})` : ''}
              </button>
              {toRemove.length > 0 && (
                <button type="button" className="market-opportunities__recompute" onClick={() => applyPriority(toRemove, 'remove')} disabled={priorityBusy}>
                  Remove from priority list ({toRemove.length})
                </button>
              )}
              <span className="market-analysis__hint">{priorityCount} on the priority list</span>
            </div>
            {isRegion && (
              <label className="global-tam__sort">
                Target country
                <select value={targetFilter} onChange={(event) => setTargetFilter(event.target.value)}>
                  <option value="">All countries</option>
                  {targetCountries.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {priorityError && <p className="market-analysis__hint">Priority list: {priorityError}</p>}
          <div className="market-opportunities__table-wrap">
            <table className="market-opportunities__table">
              <thead>
                <tr>
                  <th className="market-opportunities__check-col" aria-label="Priority list" title="Tick products, then Add to priority list" />
                  <th>Product</th>
                  <th>Target Product</th>
                  <th>HS Code</th>
                  {isRegion && <th>Target Country</th>}
                  <th>Source Price</th>
                  <th>Target Price</th>
                  <th title={SAM_SCOPE_NOTE}>Region SAM</th>
                  <th title={SAM_SCOPE_NOTE}>Country SAM</th>
                  <th>Diff %</th>
                  <th>Opportunity</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {groupedRows.map(({ rating, rows: groupRows }) => {
                  // Showing just the priority list opens every group it has.
                  const isOpen = sortKey === 'priority' || expandedRatings.has(rating)
                  const count = groupRows.length
                  const summary =
                    rating === 'Unrated'
                      ? `${count} product${count === 1 ? '' : 's'} not yet rated`
                      : `${count} product${count === 1 ? '' : 's'} rated ${rating.toLowerCase()}`
                  return (
                    <Fragment key={rating}>
                      <tr className="market-opportunities__rating-row" onClick={() => toggleRating(rating)}>
                        <td colSpan={isRegion ? 12 : 11}>
                          <div className="market-opportunities__rating-row-inner">
                            <button
                              type="button"
                              className="available-categories__row-toggle"
                              onClick={(event) => {
                                event.stopPropagation()
                                toggleRating(rating)
                              }}
                              aria-expanded={isOpen}
                              aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${rating} group`}
                            >
                              <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
                            </button>
                            <span className="market-opportunities__rating-label">{rating}</span>
                            <span className="market-opportunities__rating-summary">{summary}</span>
                          </div>
                        </td>
                      </tr>
                      {isOpen &&
                        groupRows.map((row) => (
                          <tr key={row.id} className={priority.has(priorityKey(row)) ? 'is-priority' : ''}>
                            <td className="market-opportunities__check-col">
                              <input
                                type="checkbox"
                                checked={isTicked(priorityKey(row))}
                                onChange={() => togglePriority(row)}
                                disabled={priorityBusy}
                                aria-label={`Priority: ${row.product_name}`}
                                title={priority.has(priorityKey(row)) ? 'On the priority list — untick to remove it' : 'Tick, then Add to priority list'}
                              />
                            </td>
                            <td>{row.product_name}</td>
                            <td className="market-analysis__company">{row._target_display_name || '—'}</td>
                            <td className="market-opportunities__hs-code">{row.hs_code || '—'}</td>
                            {isRegion && <td>{row.target_country}</td>}
                            <td title={row.conversion_note || ''} className="market-opportunities__price-cell">
                              <span className="market-opportunities__price-usd">{formatUsdPerKg(row.source_price_normalized)}</span>
                              <span className="market-opportunities__price-local" title={formatRateDate(row, 'source') || ''}>
                                {formatOriginal(row.source_price_original)}
                              </span>
                            </td>
                            <td title={row.conversion_note || ''} className="market-opportunities__price-cell">
                              <span className="market-opportunities__price-usd">{formatUsdPerKg(row.target_price_normalized)}</span>
                              <span className="market-opportunities__price-local" title={formatRateDate(row, 'target') || ''}>
                                {formatOriginal(row.target_price_original)}
                              </span>
                            </td>
                            <td title={samTitle(row, 'region')}>{formatSamCell(getRegionSam(row))}</td>
                            <td title={samTitle(row, 'country')}>{formatSamCell(getSamValue(row))}</td>
                            <td>{formatDiffPct(row.diff_pct)}</td>
                            <td>{row.opportunity_rating || '—'}</td>
                            <td>
                              {reviewBadges(row).length === 0
                                ? '—'
                                : reviewBadges(row).map((badge) => (
                                    <span
                                      key={badge.label}
                                      className={badge.className}
                                      title={[...(row.review_reasons || []), row.conversion_note].filter(Boolean).join(' ')}
                                    >
                                      {badge.label}
                                    </span>
                                  ))}
                            </td>
                          </tr>
                        ))}
                    </Fragment>
                  )
                })}
                {filteredSortedRows.length === 0 && (
                  <tr>
                    <td colSpan={isRegion ? 12 : 11} className="market-analysis__empty-row">
                      {sortKey === 'priority' && !search
                        ? 'No products on the priority list yet — tick products, then Add to priority list.'
                        : `No product matches "${search}".`}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {rows.length === 0 && <p className="market-analysis__hint">No products matched between {sourceCountry} and the target market — see the unmatched list below.</p>}

      {unmatchedEntries.length > 0 && (
        <div className="market-opportunities__unmatched">
          <h4>No match found in target market</h4>
          {unmatchedEntries.map(([targetCountry, list]) => {
            const isOpen = expandedUnmatched.has(targetCountry)
            return (
            <div key={targetCountry} className="market-opportunities__unmatched-group">
              <button
                type="button"
                className="market-opportunities__unmatched-head"
                onClick={() => toggleUnmatched(targetCountry)}
                aria-expanded={isOpen}
                aria-label={`${isOpen ? 'Collapse' : 'Expand'} unmatched products for ${targetCountry}`}
              >
                <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
                {isRegion && <strong>{targetCountry}</strong>}
                <span className="market-opportunities__rating-summary">
                  {list.length} product{list.length === 1 ? '' : 's'} with no match found
                </span>
              </button>
              {isOpen && (
              <ul>
                {list.map((product, index) => (
                  <li key={`${targetCountry}-${product.matchName}-${index}`}>
                    {product.displayName} <span className="market-analysis__company">({product.category || 'Uncategorized'})</span>
                  </li>
                ))}
              </ul>
              )}
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Market Opportunities: pick a Source (a country whose own Country Product
// Portfolio — Market Analysis ▸ Country Information — has at least one
// Wholesaler-labeled source with real products, built-in or custom alike),
// then narrow a Target market either to a whole region or down to one
// active country inside it. The By Country list is filtered the same way —
// a country only appears there if it has at least one Wholesaler OR Retail
// source with real products (a destination market is exactly where Retail
// data matters, unlike Source). Each dropdown is disabled until the one
// before it has a selection, and changing an earlier one clears everything
// after it — a stale downstream choice (e.g. a region picked under the old
// Target mode) must never linger once what it depended on has changed.
function MarketOpportunitiesPanel() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [sourceCountries, setSourceCountries] = useState([])
  const [portfolioCountryNames, setPortfolioCountryNames] = useState(() => new Set())
  const [regions, setRegions] = useState([])

  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [region, setRegion] = useState('')
  const [country, setCountry] = useState('')
  const [savedPairs, setSavedPairs] = useState([])

  const loadSavedPairs = useCallback(() => {
    fetchMarketOpportunityPairs()
      .then((data) => setSavedPairs(data.pairs || []))
      .catch(() => setSavedPairs([]))
  }, [])

  useEffect(() => {
    loadSavedPairs()
  }, [loadSavedPairs])

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchProductSources(), fetchMarketAnalysisRegions()])
      .then(([sources, regionRows]) => {
        if (cancelled) return
        // "Has a Country Product Portfolio and is labeled Wholesaler" — a
        // source counts only once it actually has products (product_count
        // > 0), not merely configured; built-in and custom sources are
        // exactly the same two pools Country Product Portfolio itself
        // draws from (see CustomSourceProductsView.jsx).
        const allSources = [...(sources.built_in || []), ...(sources.custom || [])]
        const wholesalerCountries = [
          ...new Set(
            allSources.filter((row) => row.analysis_type === 'wholesaler' && row.product_count > 0).map((row) => row.country_name),
          ),
        ].sort((a, b) => a.localeCompare(b))
        setSourceCountries(wholesalerCountries)
        // Same "qualifying" idea Available Categories/SAM/TAM already use
        // (real linked data, not just a configured-but-empty source) —
        // reused here rather than a second check, just widened to either
        // label: a Target country is a destination market, where Retail
        // (not just Wholesaler) is exactly the kind of source that matters.
        const portfolioNames = new Set(allSources.filter((row) => row.product_count > 0).map((row) => row.country_name.trim().toLowerCase()))
        setPortfolioCountryNames(portfolioNames)
        // "Active regions" — only ones with at least one active country;
        // an empty region has nothing to target and would be a dead end.
        const activeRegions = regionRows.filter((row) => row.countries.length > 0)
        setRegions(activeRegions)
        // ?source=Colombia&target=Jamaica (e.g. from the Shipment builder)
        // opens that comparison, By Country.
        const wantSource = searchParams.get('source')
        const wantTarget = searchParams.get('target')
        if (wantSource && wantTarget && wholesalerCountries.includes(wantSource)) {
          for (const row of activeRegions) {
            const match = row.countries.find((item) => item.name === wantTarget && portfolioNames.has(item.name.trim().toLowerCase()))
            if (match) {
              setSource(wantSource)
              setTarget('country')
              setRegion(row.region)
              setCountry(match.id)
              break
            }
          }
        }
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err?.message || 'Could not load Market Opportunities.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the address only picks the first comparison shown
  }, [])

  const handleSourceChange = (value) => {
    setSource(value)
    setTarget('')
    setRegion('')
    setCountry('')
  }

  const handleTargetChange = (value) => {
    setTarget(value)
    setRegion('')
    setCountry('')
  }

  const handleRegionChange = (value) => {
    setRegion(value)
    setCountry('')
  }

  // A saved pair opens as a By Country selection, in the region its target
  // country belongs to — null when that's not selectable here any more.
  const savedPairSelection = (pair) => {
    if (!sourceCountries.includes(pair.source_country)) return null
    for (const row of regions) {
      const match = row.countries.find((item) => item.name === pair.target_country)
      if (match && portfolioCountryNames.has(match.name.trim().toLowerCase())) return { region: row.region, countryId: match.id }
    }
    return null
  }

  const openSavedPair = (pair) => {
    const selection = savedPairSelection(pair)
    if (!selection) return
    setSource(pair.source_country)
    setTarget('country')
    setRegion(selection.region)
    setCountry(selection.countryId)
  }

  const countriesInRegion = useMemo(() => {
    const all = regions.find((row) => row.region === region)?.countries || []
    return all.filter((row) => portfolioCountryNames.has(row.name.trim().toLowerCase()))
  }, [regions, region, portfolioCountryNames])

  const selectionComplete = Boolean(source && target && region && (target === 'region' || country))

  // Target = "By Region" runs every qualifying country in the region, each
  // as its own independent source->target pair (see marketOpportunities.js);
  // Target = "By Country" runs just the one selected country — `country`
  // holds that country's id, so its name is looked up from the same
  // already-filtered countriesInRegion list the dropdown itself renders.
  const targetCountryNames = useMemo(() => {
    if (!selectionComplete) return []
    if (target === 'region') return countriesInRegion.map((row) => row.name)
    const match = countriesInRegion.find((row) => row.id === country)
    return match ? [match.name] : []
  }, [selectionComplete, target, countriesInRegion, country])

  if (status === 'loading') return <p className="market-analysis__hint">Loading Market Opportunities…</p>
  if (status === 'error') return <p className="market-analysis__hint">{error}</p>

  return (
    <div className="market-opportunities">
      <p className="market-analysis__hint">
        Pick a wholesaler-sourced country to sell from, then narrow the target market to a whole region or one
        specific country in it.
      </p>

      {savedPairs.length > 0 && (
        <div className="market-opportunities__saved">
          <span className="market-opportunities__saved-label">Saved comparisons</span>
          <div className="market-opportunities__saved-list">
            {savedPairs.map((pair) => {
              const selectable = Boolean(savedPairSelection(pair))
              const active = selectable && source === pair.source_country && target === 'country' && savedPairSelection(pair)?.countryId === country
              return (
                <button
                  key={`${pair.source_country}>${pair.target_country}`}
                  type="button"
                  className={`market-opportunities__saved-pair ${active ? 'is-active' : ''}`}
                  onClick={() => openSavedPair(pair)}
                  disabled={!selectable}
                  title={
                    selectable
                      ? `${pair.row_count} products compared — computed ${formatDateTime(pair.calculated_at)}`
                      : 'No longer selectable: the country is no longer an active source or target'
                  }
                >
                  {pair.source_country} › {pair.target_country}
                  <span className="market-opportunities__saved-date">{new Date(pair.calculated_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div className="market-opportunities__controls">
        <label className="market-opportunities__field">
          Source
          <select value={source} onChange={(event) => handleSourceChange(event.target.value)}>
            <option value="">Select a country…</option>
            {sourceCountries.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="market-opportunities__field">
          Target
          <select value={target} onChange={(event) => handleTargetChange(event.target.value)} disabled={!source}>
            <option value="">Select…</option>
            {TARGET_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="market-opportunities__field">
          Select Region
          <select value={region} onChange={(event) => handleRegionChange(event.target.value)} disabled={!target}>
            <option value="">Select a region…</option>
            {regions.map((row) => (
              <option key={row.region} value={row.region}>
                {row.region}
              </option>
            ))}
          </select>
        </label>

        {target === 'country' && (
          <label className="market-opportunities__field">
            Select Country
            <select value={country} onChange={(event) => setCountry(event.target.value)} disabled={!region}>
              <option value="">Select a country…</option>
              {countriesInRegion.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {target === 'country' && region && countriesInRegion.length === 0 && (
        <p className="market-analysis__hint">
          No country in {region} has a linked Wholesaler or Retail source with real products yet.
        </p>
      )}

      {sourceCountries.length === 0 && (
        <p className="market-analysis__hint">
          No country has a Wholesaler-labeled Country Product Portfolio yet — add one in Settings ▸ Product analysis
          sources, or relabel an existing source there.
        </p>
      )}
      {selectionComplete && targetCountryNames.length > 0 && (
        <MarketOpportunityResults
          sourceCountry={source}
          targetCountries={targetCountryNames}
          isRegion={target === 'region'}
          region={region}
          onSaved={loadSavedPairs}
        />
      )}
    </div>
  )
}

export default MarketOpportunitiesPanel
