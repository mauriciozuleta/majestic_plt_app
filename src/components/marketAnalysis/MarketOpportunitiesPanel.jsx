import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { fetchMarketAnalysisRegions } from '../../services/commercialStructure'
import { fetchProductSources } from '../../services/productSources'
import { computeMarketOpportunity, saveMarketOpportunityComparisons } from '../../services/marketOpportunities'
import { buildCategoryCoverage } from '../../services/productPortfolio'
import { fetchSamOverview } from '../../services/globalTradeData'
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
  { key: 'sam_desc', label: 'SAM (High to Low)' },
  { key: 'sam_asc', label: 'SAM (Low to High)' },
]

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

// Results: runs computeMarketOpportunity() (src/services/marketOpportunities.js)
// for the current source/target selection, persists the scored rows (Step
// 3/5 of the spec — backend computes diff_pct/opportunity_rating/
// match_confidence, this just merges the display-only target product name
// back in by array position, since the POST preserves row order), and
// renders a sortable/filterable table plus the separate "no match found in
// target market" list. Recomputes whenever the selection actually changes
// (source/targetCountries) — a fresh run each time, not an incremental
// patch, same convention the backend's own overwrite-on-save already uses.
function MarketOpportunityResults({ sourceCountry, targetCountries, isRegion, region }) {
  const [runStatus, setRunStatus] = useState('idle')
  const [runError, setRunError] = useState(null)
  const [aiMatchErrors, setAiMatchErrors] = useState({})
  const [rows, setRows] = useState([])
  const [unmatchedByTarget, setUnmatchedByTarget] = useState({})
  const [calculatedAt, setCalculatedAt] = useState(null)
  const [sortKey, setSortKey] = useState('rating')
  const [search, setSearch] = useState('')
  const [targetFilter, setTargetFilter] = useState('')
  // SAM, by 2-digit HS chapter, scoped to the region this run's countries
  // actually belong to (both Target modes only ever draw from one region —
  // Select Country only lists countries inside the already-selected
  // region). `regionTotal` is SAM's own region-level chapter total; `byCountry`
  // is that same chapter's per-country breakdown within it — which one a
  // row shows depends on whether this run is "By Region" or "By Country"
  // (see the SAM cell below), never both blended into one figure.
  const [samByChapter, setSamByChapter] = useState(new Map())

  useEffect(() => {
    let cancelled = false
    buildCategoryCoverage()
      .then((coverage) => {
        const chapterList = Object.keys(coverage)
        if (chapterList.length === 0) return null
        return fetchSamOverview(chapterList)
      })
      .then((data) => {
        if (cancelled || !data) return
        const regionData = (data.regions || []).find((row) => row.region === region)
        const map = new Map()
        ;(regionData?.categories || []).forEach((category) => {
          map.set(category.chapter, {
            regionTotal: category.value,
            byCountry: new Map((category.countries || []).map((c) => [c.name, c.value])),
          })
        })
        setSamByChapter(map)
      })
      .catch(() => {
        // SAM is a supplementary figure here — its own tab already surfaces
        // load errors; this column just shows "—" rather than blocking the
        // comparison table over it.
      })
    return () => {
      cancelled = true
    }
  }, [region])
  // Which rating groups are expanded — same "starts collapsed, click to
  // open" convention as this app's other collapsible sections
  // (AvailableCategoriesPanel's HS sections, GlobalTamPanel's category
  // cards): empty Set means every group starts collapsed.
  const [expandedRatings, setExpandedRatings] = useState(() => new Set())

  const targetKey = targetCountries.join('|')

  useEffect(() => {
    if (!sourceCountry || targetCountries.length === 0) return undefined
    let cancelled = false
    setRunStatus('running')
    setRunError(null)
    computeMarketOpportunity(sourceCountry, targetCountries)
      .then(async ({ rows: computedRows, unmatchedByTarget: unmatched, aiMatchErrors: aiErrors }) => {
        if (cancelled) return
        setAiMatchErrors(aiErrors || {})
        if (computedRows.length === 0) {
          setRows([])
          setUnmatchedByTarget(unmatched)
          setCalculatedAt(new Date().toISOString())
          setRunStatus('ready')
          return
        }
        const payload = computedRows.map(({ _target_display_name, ...rest }) => rest)
        const saved = await saveMarketOpportunityComparisons(payload)
        if (cancelled) return
        const merged = saved.rows.map((row, index) => ({ ...row, _target_display_name: computedRows[index]?._target_display_name }))
        setRows(merged)
        setUnmatchedByTarget(unmatched)
        setCalculatedAt(saved.calculated_at)
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
  }, [sourceCountry, targetKey])

  // SAM for this row's own 2-digit chapter — the REGION total in a "By
  // Region" run (every target country in the run belongs to it), or that
  // specific target country's own contribution to it in a "By Country" run
  // — never both, matching whichever scope the current selection is
  // actually in. Null when the product isn't classified yet, or SAM hasn't
  // been computed for this region/chapter at all. Defined before
  // filteredSortedRows below (not just for readability — its useMemo
  // callback runs synchronously this render and would otherwise reference
  // this function before it's assigned).
  const getSamValue = useCallback(
    (row) => {
      const chapter = row.hs_code ? row.hs_code.slice(0, 2) : null
      if (!chapter) return null
      const entry = samByChapter.get(chapter)
      if (!entry) return null
      return isRegion ? entry.regionTotal : (entry.byCountry.get(row.target_country) ?? null)
    },
    [samByChapter, isRegion],
  )

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
  }, [rows, search, targetFilter, sortKey, getSamValue])

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

  if (runStatus === 'idle' || runStatus === 'running') {
    return <p className="market-analysis__hint">Comparing {sourceCountry}'s prices against {targetCountries.length > 1 ? `${targetCountries.length} countries` : targetCountries[0]}…</p>
  }
  if (runStatus === 'error') return <p className="market-analysis__hint">{runError}</p>

  return (
    <div className="market-opportunities__results">
      <p className="market-analysis__hint">
        {rows.length} matched product{rows.length === 1 ? '' : 's'} compared, {totalUnmatched} with no match found in
        the target market. {calculatedAt && `Last computed: ${new Date(calculatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}.`}
      </p>
      {Object.entries(aiMatchErrors).map(([country, message]) => (
        <p key={country} className="market-analysis__hint">
          AI matching for {country} didn't run ({message}) — only exact-name, curated and shared-HS-code matches are shown.
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

          <div className="market-opportunities__table-wrap">
            <table className="market-opportunities__table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Target Product</th>
                  <th>HS Code</th>
                  {isRegion && <th>Target Country</th>}
                  <th>Source Price</th>
                  <th>Target Price</th>
                  <th>SAM</th>
                  <th>Diff %</th>
                  <th>Opportunity</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {groupedRows.map(({ rating, rows: groupRows }) => {
                  const isOpen = expandedRatings.has(rating)
                  const count = groupRows.length
                  const summary =
                    rating === 'Unrated'
                      ? `${count} product${count === 1 ? '' : 's'} not yet rated`
                      : `${count} product${count === 1 ? '' : 's'} rated ${rating.toLowerCase()}`
                  return (
                    <Fragment key={rating}>
                      <tr className="market-opportunities__rating-row" onClick={() => toggleRating(rating)}>
                        <td colSpan={isRegion ? 10 : 9}>
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
                          <tr key={row.id}>
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
                            <td>{formatSam(getSamValue(row))}</td>
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
                    <td colSpan={isRegion ? 10 : 9} className="market-analysis__empty-row">
                      No product matches "{search}".
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
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [sourceCountries, setSourceCountries] = useState([])
  const [portfolioCountryNames, setPortfolioCountryNames] = useState(() => new Set())
  const [regions, setRegions] = useState([])

  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [region, setRegion] = useState('')
  const [country, setCountry] = useState('')

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
        setPortfolioCountryNames(
          new Set(allSources.filter((row) => row.product_count > 0).map((row) => row.country_name.trim().toLowerCase())),
        )
        // "Active regions" — only ones with at least one active country;
        // an empty region has nothing to target and would be a dead end.
        setRegions(regionRows.filter((row) => row.countries.length > 0))
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
        <MarketOpportunityResults sourceCountry={source} targetCountries={targetCountryNames} isRegion={target === 'region'} region={region} />
      )}
    </div>
  )
}

export default MarketOpportunitiesPanel
