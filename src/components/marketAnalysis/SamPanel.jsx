import { Fragment, useEffect, useState } from 'react'
import { HS_CHAPTERS } from './hsChaptersCatalog'
import { buildCategoryCoverage } from '../../services/productPortfolio'
import { fetchSamOverview, fetchSamOverviewEstimates } from '../../services/globalTradeData'
import { formatCurrencyValue } from '../../utils/currencyFormat'

// SAM used to have its own Overview/Custom sub-tabs one level inside the
// Market Size ▸ SAM tab; Custom was always a stub and has been removed
// (see MARKET_SIZING_METHODOLOGY.md) — with only Overview left, SamPanel
// now renders it directly, no nested tab bar. (SAM is what this whole
// panel used to call "TAM" — corrected once TAM was redefined as unscoped
// global demand; see MARKET_SIZING_METHODOLOGY.md for why.)

function chapterName(code) {
  return HS_CHAPTERS.find((row) => row.hs_chapter === code)?.chapter_name || `Chapter ${code}`
}

function money(value) {
  // Comtrade's own primaryValue is already in USD — no local-currency
  // amount exists to pair it with here, unlike a country-specific figure
  // elsewhere in the app (see currencyFormat.js's own dual-currency rule).
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// GDP-per-capita is still a USD amount (same code-before-$ convention as
// every other currency figure in this app), just shown with cents since
// per-capita figures are small enough for them to matter — unlike a
// region/category total, which is always whole dollars via money() above.
function moneyPerCapita(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCount(value) {
  return Number(value).toLocaleString('en-US')
}

function formatWhen(iso) {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function modelDescription(model) {
  const method = model.method === 'log-log' ? 'Log-log' : 'Linear'
  return `${method} regression on population + GDP per capita, R² ${model.r_squared.toFixed(2)} (trained on ${model.sample_size} confirmed ${model.sample_size === 1 ? 'country' : 'countries'})`
}

// One estimated country's breakdown row + its own expandable transparency
// panel — predicted value, the model's R²/method, which real countries
// trained it, and the exact population/GDP-per-capita inputs used for THIS
// country's prediction. Kept as a second, visually distinct row style from
// a confirmed/bilateral country row (see .sam-overview__row--estimated in
// MarketAnalysisView.css) so an estimated figure is never mistaken for a
// reported one, even before reading its badge.
function EstimatedCountryRow({ country, model, isOpen, onToggle }) {
  return (
    <Fragment>
      <tr className="sam-overview__row sam-overview__row--country sam-overview__row--estimated">
        <td />
        <td className="sam-overview__country-name" colSpan={2}>
          <button
            type="button"
            className="sam-overview__estimate-toggle"
            onClick={onToggle}
            aria-expanded={isOpen}
            aria-label={`${isOpen ? 'Hide' : 'Show'} estimate details for ${country.name}`}
          >
            <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
            {country.name}
          </button>
        </td>
        <td className="sam-overview__value">
          {money(country.predicted_value)}
          <span
            className={`market-analysis__estimated-badge ${country.low_confidence ? 'market-analysis__estimated-badge--low-confidence' : ''}`}
            title={country.low_confidence ? "Modeled value from a model whose R² is below the 0.50 confidence guardrail — shown because you've opted in, but treat it as a rough order of magnitude, not a reliable figure." : 'A modeled value, not a reported one — see the expanded detail for the model and inputs behind it.'}
          >
            {country.low_confidence ? 'Estimated · Low Confidence' : 'Estimated'}
          </span>
        </td>
      </tr>
      {isOpen && (
        <tr className="sam-overview__row sam-overview__row--estimate-detail">
          <td />
          <td colSpan={3} className="sam-overview__estimate-detail">
            <div>{modelDescription(model)}</div>
            <div>Trained on: {model.trained_countries.map((c) => c.name).join(', ')}</div>
            <div>
              This country's inputs: population {formatCount(country.population)} ({country.population_year}) · GDP per
              capita {moneyPerCapita(country.gdp_per_capita)} ({country.gdp_per_capita_year})
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  )
}

// The category row's own value cell — three shapes depending on the toggle
// and what the estimation layer found for this chapter:
//   1. Toggle off, or no estimate data yet for this chapter: exactly the
//      original single confirmed figure (+ bilateral badge), unchanged.
//   2. Toggle on, guardrail failed (fewer than the minimum confirmed
//      countries): the confirmed figure, PLUS the guardrail explanation in
//      place of an estimate — never a silently missing category.
//   3. Toggle on, a model was fit: "Confirmed: $X" and
//      "Confirmed + Estimated: $Y" side by side, never blended into one
//      number, tagged with the model's own confidence.
function CategoryValueCell({ category }) {
  const estimate = category.estimate
  if (!estimate) {
    return (
      <>
        {money(category.value)}
        {category.bilateral && (
          <span
            className="market-analysis__bilateral-badge"
            title="At least one contributing country's figure comes from bilateral-only coverage, not total trade with the world."
          >
            Bilateral
          </span>
        )}
      </>
    )
  }

  if (estimate.status === 'insufficient_confirmed_data') {
    return (
      <div className="sam-overview__dual-total">
        <div>
          Confirmed: {money(category.value)}
          {category.bilateral && <span className="market-analysis__bilateral-badge">Bilateral</span>}
        </div>
        <div className="sam-overview__estimate-guardrail">{estimate.message}</div>
      </div>
    )
  }

  const estimatedTotal = category.value + estimate.estimates.reduce((sum, item) => sum + item.predicted_value, 0)
  return (
    <div className="sam-overview__dual-total">
      <div>
        Confirmed: {money(category.value)}
        {category.bilateral && <span className="market-analysis__bilateral-badge">Bilateral</span>}
      </div>
      <div>
        Confirmed + Estimated: {money(estimatedTotal)}
        <span
          className={`market-analysis__estimated-badge ${estimate.model.low_confidence ? 'market-analysis__estimated-badge--low-confidence' : ''}`}
          title={modelDescription(estimate.model)}
        >
          {estimate.model.low_confidence ? 'Modeled · Low Confidence' : 'Modeled'}
        </span>
      </div>
    </div>
  )
}

// One region's card: every qualifying category that actually had at least
// one contributing country (confirmed OR, with the toggle on, an estimate
// worth showing), its region total(s), and an expandable per-country
// breakdown — same chevron-toggle interaction AvailableCategoriesPanel uses
// for its own chapter/heading/subheading rows (reusing its exact
// .available-categories__row-toggle/__chevron classes rather than a new
// toggle control).
function RegionCard({ region, expanded, onToggle, expandedEstimates, onToggleEstimate }) {
  return (
    <div className="sam-overview__card">
      <h5 className="sam-overview__card-title">
        {region.region}
        <span className="sam-overview__card-count">
          {region.categories.length} {region.categories.length === 1 ? 'category' : 'categories'}
        </span>
      </h5>
      <table className="sam-overview__table">
        <tbody>
          {region.categories.map((category) => {
            const key = `${region.region}:${category.chapter}`
            const isOpen = expanded.has(key)
            const estimate = category.estimate
            const hasEstimateRows = estimate?.status === 'estimated' && estimate.estimates.length > 0
            return (
              <Fragment key={key}>
                <tr className="sam-overview__row">
                  <td className="sam-overview__toggle-cell">
                    <button
                      type="button"
                      className="available-categories__row-toggle"
                      onClick={() => onToggle(key)}
                      aria-expanded={isOpen}
                      aria-label={`${isOpen ? 'Collapse' : 'Expand'} category ${category.chapter}`}
                    >
                      <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
                    </button>
                  </td>
                  <td className="sam-overview__code">{category.chapter}</td>
                  <td className="sam-overview__name">{chapterName(category.chapter)}</td>
                  <td className="sam-overview__value">
                    <CategoryValueCell category={category} />
                  </td>
                </tr>
                {isOpen &&
                  category.countries.map((country) => (
                    <tr key={country.id} className="sam-overview__row sam-overview__row--country">
                      <td />
                      <td className="sam-overview__country-name" colSpan={2}>
                        {country.name}
                        <span className="sam-overview__country-year">{country.year}</span>
                      </td>
                      <td className="sam-overview__value">
                        {money(country.value)}
                        {country.bilateral && <span className="market-analysis__bilateral-badge">Bilateral</span>}
                      </td>
                    </tr>
                  ))}
                {isOpen &&
                  hasEstimateRows &&
                  estimate.estimates.map((country) => {
                    const estimateKey = `${key}:${country.id}`
                    return (
                      <EstimatedCountryRow
                        key={estimateKey}
                        country={country}
                        model={estimate.model}
                        isOpen={expandedEstimates.has(estimateKey)}
                        onToggle={() => onToggleEstimate(estimateKey)}
                      />
                    )
                  })}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// SAM Overview: real UN Comtrade import totals for every "green" category —
// any HS chapter with actual product data in Available Categories (see
// buildCategoryCoverage, services/productPortfolio.js) — summed per region
// from only the countries that actually reported that chapter, at each
// country's own most-recently-reported year. All the real aggregation work
// (year resolution, per-country/per-chapter sums, the bilateral-coverage
// flag) happens server-side (see backend/routers/comtrade.py's
// sam_overview) — this panel only decides WHICH chapters qualify (a
// frontend-only computation, see buildCategoryCoverage's own doc-comment
// for why) and renders what comes back.
//
// The "Include estimated values (modeled)" toggle is OFF by default and
// changes nothing about this default path — it only ever adds a second,
// separately-fetched layer (backend/routers/comtrade.py's
// sam_overview_estimates, see MARKET_SIZING_METHODOLOGY.md) on top, never blended
// into the confirmed numbers above.
function SamOverviewPanel() {
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [regions, setRegions] = useState([])
  const [chapters, setChapters] = useState([])
  const [computedAt, setComputedAt] = useState(null)
  const [expanded, setExpanded] = useState(() => new Set())

  // Checked by default — SAM's confirmed figures alone often understate
  // coverage (a region with real product demand but few Comtrade-covered
  // countries), so estimated values now show automatically rather than
  // requiring a click. This only changes the default; the toggle still
  // fetches sam-overview-estimates itself (see the effect below), and that
  // layer stays un-persisted — see MARKET_SIZING_METHODOLOGY.md §1.4/§1.6.
  const [includeEstimates, setIncludeEstimates] = useState(true)
  const [estimatesStatus, setEstimatesStatus] = useState('idle')
  const [estimatesError, setEstimatesError] = useState(null)
  const [estimatesRegions, setEstimatesRegions] = useState([])
  const [expandedEstimates, setExpandedEstimates] = useState(() => new Set())

  useEffect(() => {
    // Runs once on mount (empty deps below) — status/error already start at
    // their loading/null defaults above, so there's nothing to reset here;
    // this effect only ever moves forward into 'ready' or 'error'.
    let cancelled = false
    buildCategoryCoverage()
      .then((coverage) => {
        const chapterList = Object.keys(coverage)
        setChapters(chapterList)
        if (chapterList.length === 0) return null
        return fetchSamOverview(chapterList)
      })
      .then((data) => {
        if (cancelled) return
        setRegions(data?.regions || [])
        setComputedAt(data?.computed_at || null)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err?.message || 'Could not load the SAM overview.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    // Fetches the estimation layer exactly once, the first time the toggle
    // is switched on (guarded by estimatesStatus !== 'idle' — the only two
    // states that async .then/.catch below ever moves it to are 'ready' and
    // 'error', so this never re-fires after the first successful/failed
    // fetch). Switching the toggle back off just hides what's already
    // loaded rather than discarding and refetching it; turning it on again
    // is instant. `estimatesStatus` staying 'idle' while includeEstimates is
    // true (below, in the render) IS the loading state — deliberately not
    // set synchronously from here, only from the async callbacks.
    if (!includeEstimates || estimatesStatus !== 'idle' || chapters.length === 0) return
    let cancelled = false
    fetchSamOverviewEstimates(chapters)
      .then((data) => {
        if (cancelled) return
        setEstimatesRegions(data?.regions || [])
        setEstimatesStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setEstimatesError(err?.message || 'Could not load estimated values.')
        setEstimatesStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [includeEstimates, estimatesStatus, chapters])

  const toggle = (key) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleEstimateDetail = (key) => {
    setExpandedEstimates((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Merges the confirmed-only regions above with the estimation layer's own
  // per-chapter results, region by region — never mutating the confirmed
  // numbers themselves, only attaching each category's `estimate` (null
  // until the toggle's own fetch resolves). With the toggle on, a chapter
  // that had ZERO confirmed/bilateral countries anywhere in a region (and
  // so never appeared in the confirmed-only view at all) is also surfaced
  // here IF the estimation layer has something to say about it (either a
  // real model's estimates, or the guardrail explanation) — "never a
  // silently missing row" applies to those too, not just chapters that
  // already had a confirmed total.
  const estimatesByRegion = new Map(estimatesRegions.map((region) => [region.region, region]))
  const mergedRegions = regions.map((region) => {
    const estimateRegion = estimatesByRegion.get(region.region)
    const estimateByChapter = new Map((estimateRegion?.categories || []).map((category) => [category.chapter, category]))
    const confirmedChapters = new Set(region.categories.map((category) => category.chapter))

    const categories = region.categories.map((category) => ({
      ...category,
      estimate: estimateByChapter.get(category.chapter) || null,
    }))

    if (includeEstimates) {
      chapters.forEach((chapter) => {
        if (confirmedChapters.has(chapter)) return
        const estimate = estimateByChapter.get(chapter)
        if (!estimate) return
        if (estimate.status === 'estimated' && estimate.estimates.length === 0) return
        categories.push({ chapter, value: 0, bilateral: false, countries: [], estimate })
      })
    }

    return { ...region, categories }
  })

  const cardRegions = mergedRegions.filter((region) => region.categories.length > 0)

  return (
    <div className="sam-overview">
      <p className="market-analysis__hint">
        Serviceable Available Market — real UN Comtrade import totals (2-digit chapter aggregates, not just the sum of
        classified products) for every category with real product data in Available Categories, summed per region
        from the countries that actually reported it.
      </p>
      <p className="market-analysis__hint">
        {computedAt
          ? `Last updated: ${formatWhen(computedAt)}. `
          : ''}
        Ask the assistant to "refresh SAM" to recompute this with the latest UN Comtrade data.
      </p>
      <label className="sam-overview__estimate-control">
        <input
          type="checkbox"
          checked={includeEstimates}
          onChange={(event) => setIncludeEstimates(event.target.checked)}
        />
        Include estimated values (modeled)
      </label>
      {includeEstimates && estimatesStatus === 'idle' && (
        <p className="market-analysis__hint">Loading estimated values…</p>
      )}
      {includeEstimates && estimatesStatus === 'error' && <p className="market-analysis__hint">{estimatesError}</p>}
      {status === 'loading' && <p className="market-analysis__hint">Loading SAM overview…</p>}
      {status === 'error' && <p className="market-analysis__hint">{error}</p>}
      {status === 'ready' && cardRegions.length === 0 && (
        <p className="market-analysis__hint">
          No qualifying category has reported UN Comtrade import data yet for any region's active countries.
        </p>
      )}
      {status === 'ready' && cardRegions.length > 0 && (
        <div className="sam-overview__cards">
          {cardRegions.map((region) => (
            <RegionCard
              key={region.region}
              region={region}
              expanded={expanded}
              onToggle={toggle}
              expandedEstimates={expandedEstimates}
              onToggleEstimate={toggleEstimateDetail}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// SAM tab's own content — just Overview now (Custom was a stub and has
// been removed, see MARKET_SIZING_METHODOLOGY.md), so no nested tab bar is
// rendered anymore, just the Overview content directly. See
// MarketAnalysisView.jsx, which renders this for marketSizeTab === 'sam'.
// TAM and SOM are untouched siblings, not part of this component at all.
function SamPanel() {
  return (
    <div className="sam-panel">
      <div className="market-analysis__tab-panel market-analysis__tab-panel--nested">
        <SamOverviewPanel />
      </div>
    </div>
  )
}

export default SamPanel
