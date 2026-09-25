import { useEffect, useMemo, useState } from 'react'
import { HS_CHAPTERS } from './hsChaptersCatalog'
import { buildCategoryCoverage } from '../../services/productPortfolio'
import { fetchTamGlobalOverview } from '../../services/globalTradeData'
import { formatCurrencyValue } from '../../utils/currencyFormat'

// TAM used to have its own Overview/Custom sub-tabs one level inside the
// Market Size ▸ TAM tab; Custom was always a stub and has been removed
// (see MARKET_SIZING_METHODOLOGY.md) — with only Overview left,
// GlobalTamPanel now renders it directly, no nested tab bar.

const SORT_OPTIONS = [
  { key: 'value', label: 'Value (high to low)' },
  { key: 'name', label: 'Name (A-Z)' },
]

function chapterName(code) {
  return HS_CHAPTERS.find((row) => row.hs_chapter === code)?.chapter_name || `Chapter ${code}`
}

function money(value) {
  // Comtrade's own primaryValue is already in USD — same convention as
  // SAM Overview's own money() (SamPanel.jsx).
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function formatCount(value) {
  return Number(value).toLocaleString('en-US')
}

function formatWhen(iso) {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// One qualifying category's card: its global total, how many countries
// actually contributed (never omitted — a bare dollar figure with no N
// would misrepresent how complete the underlying data is), and an
// expandable, searchable, sortable per-country breakdown. No bilateral/
// partial-coverage badge here — that concept is specific to the fallback-
// source system built for SAM's tracked countries; at global scale a
// country either reported to Comtrade for this category/year or it
// didn't, and the N count already says which.
function CategoryCard({ category, isOpen, onToggle, search, onSearchChange, sort, onSortChange }) {
  const countries = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const filtered = needle ? category.countries.filter((c) => c.name.toLowerCase().includes(needle)) : category.countries
    const sorted = [...filtered]
    if (sort === 'name') sorted.sort((a, b) => a.name.localeCompare(b.name))
    else sorted.sort((a, b) => b.value - a.value)
    return sorted
  }, [category.countries, search, sort])

  return (
    <div className="global-tam__card">
      <button type="button" className="global-tam__card-head" onClick={onToggle} aria-expanded={isOpen}>
        <span className={`available-categories__chevron ${isOpen ? 'is-open' : ''}`}>▸</span>
        <span className="global-tam__card-code">{category.chapter}</span>
        <span className="global-tam__card-name">{chapterName(category.chapter)}</span>
        <span className="global-tam__card-total">
          Global TAM: {money(category.value)}
          <span className="global-tam__card-count"> (based on {formatCount(category.country_count)} reporting countries, {category.year})</span>
        </span>
      </button>
      {isOpen && (
        <div className="global-tam__card-body">
          <div className="global-tam__controls">
            <label className="available-categories__search">
              Search countries
              <input
                type="text"
                value={search}
                placeholder="Search by country name…"
                onChange={(event) => onSearchChange(event.target.value)}
              />
            </label>
            <label className="global-tam__sort">
              Sort
              <select value={sort} onChange={(event) => onSortChange(event.target.value)}>
                {SORT_OPTIONS.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {countries.length === 0 ? (
            <p className="market-analysis__hint">No country matches "{search}".</p>
          ) : (
            <div className="global-tam__table-wrap">
              <table className="global-tam__table">
                <tbody>
                  {countries.map((country) => (
                    <tr key={country.reporter_code} className="global-tam__row">
                      <td className="global-tam__country-name">{country.name}</td>
                      <td className="global-tam__value">{money(country.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// TAM Overview: real, UNSCOPED global UN Comtrade import totals for every
// "green" category — the same qualifying chapters SAM uses (see
// buildCategoryCoverage, services/productPortfolio.js), summed across
// EVERY country that reported that chapter worldwide, not just this app's
// tracked Commercial Structure countries. No regions here — this figure
// isn't scoped to any one region by definition, unlike SAM. All the real
// aggregation (year resolution, the duplicate-row guard) happens
// server-side (see backend/routers/comtrade.py's tam_global_overview) —
// this panel only decides WHICH chapters qualify (a frontend-only
// computation, see buildCategoryCoverage's own doc-comment for why) and
// renders what comes back.
function GlobalTamOverviewPanel() {
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [categories, setCategories] = useState([])
  const [computedAt, setComputedAt] = useState(null)
  const [expanded, setExpanded] = useState(() => new Set())
  const [searchByChapter, setSearchByChapter] = useState({})
  const [sortByChapter, setSortByChapter] = useState({})

  useEffect(() => {
    let cancelled = false
    buildCategoryCoverage()
      .then((coverage) => {
        const chapterList = Object.keys(coverage)
        if (chapterList.length === 0) return null
        return fetchTamGlobalOverview(chapterList)
      })
      .then((data) => {
        if (cancelled) return
        setCategories(data?.categories || [])
        setComputedAt(data?.computed_at || null)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err?.message || 'Could not load the global TAM overview.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const toggle = (chapter) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(chapter)) next.delete(chapter)
      else next.add(chapter)
      return next
    })
  }

  return (
    <div className="global-tam">
      <p className="market-analysis__hint">
        Total Addressable Market — real, unscoped UN Comtrade import totals for every category with real product
        data in Available Categories, summed across every country that reported it worldwide (not just the
        countries tracked in Commercial Structure — see Market Size ▸ SAM for that narrower figure).
      </p>
      <p className="market-analysis__hint">
        {computedAt
          ? `Last updated: ${formatWhen(computedAt)}. `
          : ''}
        Ask the assistant to "refresh TAM" to recompute this with the latest UN Comtrade data.
      </p>
      {status === 'loading' && <p className="market-analysis__hint">Loading global TAM overview…</p>}
      {status === 'error' && <p className="market-analysis__hint">{error}</p>}
      {status === 'ready' && categories.length === 0 && (
        <p className="market-analysis__hint">No qualifying category has reported UN Comtrade import data yet, anywhere.</p>
      )}
      {status === 'ready' && categories.length > 0 && (
        <div className="global-tam__cards">
          {categories.map((category) => (
            <CategoryCard
              key={category.chapter}
              category={category}
              isOpen={expanded.has(category.chapter)}
              onToggle={() => toggle(category.chapter)}
              search={searchByChapter[category.chapter] || ''}
              onSearchChange={(value) => setSearchByChapter((current) => ({ ...current, [category.chapter]: value }))}
              sort={sortByChapter[category.chapter] || 'value'}
              onSortChange={(value) => setSortByChapter((current) => ({ ...current, [category.chapter]: value }))}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// TAM tab's own content — just Overview now (Custom was a stub and has been
// removed, see MARKET_SIZING_METHODOLOGY.md), so no nested tab bar is
// rendered anymore, just the Overview content directly. See
// MarketAnalysisView.jsx, which renders this for marketSizeTab === 'tam'.
// SAM and SOM are untouched siblings, not part of this component at all.
function GlobalTamPanel() {
  return (
    <div className="global-tam-panel">
      <div className="market-analysis__tab-panel market-analysis__tab-panel--nested">
        <GlobalTamOverviewPanel />
      </div>
    </div>
  )
}

export default GlobalTamPanel
