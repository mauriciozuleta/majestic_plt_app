import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchHsProductCatalog,
  fetchTradeCategories,
  fetchTradeCountries,
  fetchTradeProducts,
  fetchTradeSourceStatus,
  fetchTradeSubheadings,
  recheckTradeSource,
} from '../../services/globalTradeData'
import { fetchMarketAnalysisRegions, fetchReferenceRegions } from '../../services/commercialStructure'
import { formatCurrencyValue } from '../../utils/currencyFormat'
import './GlobalTradeDataView.css'

function normalizeRegionName(name) {
  return (name || '').trim().toLowerCase()
}

const YEARS_BACK = 9
const MIN_SEARCH_CHARS = 2
const MAX_SEARCH_RESULTS = 12
// How many years to try, newest first, when picking a starting year for a
// country: Comtrade's default_year is only "worth trying first", not a
// guarantee — a small territory can lag several years behind a larger one.
const YEAR_PROBE_ATTEMPTS = 6

function formatValue(value) {
  return formatCurrencyValue(value, 'USD', { maximumFractionDigits: 0, minimumFractionDigits: 0 })
}

function EmptyState({ children }) {
  return <p className="global-trade__hint">{children}</p>
}

// How long to wait between polls of a country's discovery status while a
// re-check's fallback chain is running in the background (see
// backend/trade_sources/discovery.py) — the chain is a multi-step
// external-fetch job, not something worth polling faster than this.
const SOURCE_STATUS_POLL_MS = 3000

const TRADE_SOURCE_LABELS = {
  comtrade: 'UN Comtrade',
  tci_statistics_authority: 'Turks and Caicos Islands Statistics Authority',
  cbs_netherlands: 'Statistics Netherlands (CBS)',
  us_census_fred: 'US Census / FRED (bilateral)',
  none_found: 'No trade data source found',
}

function tradeSourceLabel(source) {
  return TRADE_SOURCE_LABELS[source] ?? 'UN Comtrade'
}

// The bilateral-coverage flag (see CountryReferenceCatalog.trade_data_coverage,
// discovered once per country by backend/trade_sources/discovery.py) must
// never look like Comtrade-level total coverage — rendered as a hard-to-miss
// banner, not small text, everywhere this country's trade data is shown
// (category table, product drill-down, subheading drill-down).
function BilateralCoverageBanner({ note }) {
  return (
    <div className="global-trade__bilateral-banner" role="note">
      <span className="global-trade__bilateral-banner-tag">Partial coverage — bilateral only</span>
      <p>{note || "This source only covers this territory's trade with one partner country, not its total trade with the world."}</p>
    </div>
  )
}

// Global Trade Data: UN Comtrade import/export figures by country and HS
// product category. A global module — not scoped to any one company, the
// same way Home/Control dashboard/Simulations aren't — reachable from its
// own sidebar entry regardless of which company is currently selected. All
// calls go through our backend (services/globalTradeData.js); the Comtrade
// subscription key never touches the browser.
function GlobalTradeDataView() {
  // A link into this page (the Market Analysis table's Global Trade Data
  // columns, for one) can preselect a country and flow via ?country=<code>
  // &flow=M|X — read once as initial state, then this page owns its own
  // controls same as always; nothing here keeps the URL in sync afterward.
  const [searchParams] = useSearchParams()
  const requestedCountry = searchParams.get('country')
  const requestedFlow = searchParams.get('flow')

  const [countries, setCountries] = useState([])
  const [defaultYear, setDefaultYear] = useState(null)
  const [countriesStatus, setCountriesStatus] = useState('loading')
  // Same region grouping Commercial Structure uses (CountryReferenceCatalog,
  // joined onto each Comtrade country server-side by ISO alpha-2 — see
  // routers/comtrade.py). Narrowed to regions that actually have at least
  // one country assigned somewhere in Commercial Structure, per the
  // module's own "only show regions already in use" design — a region with
  // nothing set up yet would otherwise just be an empty/irrelevant option.
  // This never restricts which COUNTRY can be picked once a region is
  // selected, or what data can be fetched for it — see countriesInRegion
  // and activeCountryCodes below.
  const [regions, setRegions] = useState([])
  const [region, setRegion] = useState('')
  // ISO alpha-2 codes already assigned to a company in Commercial Structure
  // (portfolio-wide, not just one company) — used only to color-highlight
  // those options in the country dropdown so it's obvious at a glance which
  // ones are already set up; every other country in the region is still
  // fully selectable and queries identically either way.
  const [activeCountryCodes, setActiveCountryCodes] = useState(new Set())

  const [country, setCountry] = useState('')
  // 'idle' | 'working' — 'working' only while the recheck-source POST
  // itself is in flight, not for the (possibly much longer) background
  // discovery chain it may kick off; that's tracked per-country instead,
  // via each country's own `discovering` flag (see the poll effect below).
  const [recheckStatus, setRecheckStatus] = useState('idle')
  const [recheckError, setRecheckError] = useState(null)
  const [year, setYear] = useState('')
  // True while probing backward for a year that actually has data for the
  // current country (see the effect below) — the year selector shows
  // nothing meaningful until this resolves once.
  const [resolvingYear, setResolvingYear] = useState(false)
  const [flow, setFlow] = useState(requestedFlow === 'X' ? 'X' : 'M')

  const [categories, setCategories] = useState({ status: 'idle', hasData: false, rows: [] })
  // Three mutually exclusive views, one level deeper each time — never more
  // than one showing at once. null/null: categories. selectedChapter set,
  // selectedHeading null: that chapter's 4-digit products. Both set: that
  // heading's 6-digit subheadings — the final drill-down level (6-digit is
  // the deepest HS level Comtrade publishes at all).
  const [selectedChapter, setSelectedChapter] = useState(null)
  const [products, setProducts] = useState({ status: 'idle', hasData: false, rows: [] })
  const [selectedHeading, setSelectedHeading] = useState(null)
  const [subheadings, setSubheadings] = useState({ status: 'idle', hasData: false, rows: [] })
  // Set only when a view was opened via search, so that one row can be
  // highlighted once its table loads; cleared on any other navigation so an
  // old highlight never lingers on an unrelated chapter/heading.
  const [highlightHsCode, setHighlightHsCode] = useState(null)

  // The full 4-digit HS catalog, fetched once and matched against entirely
  // client-side as the user types — never re-fetched per keystroke, and
  // never touches Comtrade's own (quota-limited) data API.
  const [catalog, setCatalog] = useState([])
  const [searchTerm, setSearchTerm] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const searchBoxRef = useRef(null)

  useEffect(() => {
    Promise.all([
      fetchTradeCountries(),
      fetchReferenceRegions().catch(() => []),
      fetchMarketAnalysisRegions().catch(() => []),
    ])
      .then(([tradeData, referenceRegions, marketRegions]) => {
        const inUseRegionNames = new Set(marketRegions.map((row) => normalizeRegionName(row.region)))
        const activeCodes = new Set(
          marketRegions
            .flatMap((row) => row.countries.map((item) => (item.country_code || '').trim().toUpperCase()))
            .filter(Boolean),
        )

        const requested = tradeData.countries.find((item) => String(item.reporter_code) === requestedCountry)
        const initialCountry = requested ?? tradeData.countries[0]

        // Falls back to every region (not just in-use ones) when nothing's
        // assigned anywhere yet — an empty Commercial Structure shouldn't
        // leave this page with no region to pick and so no way to reach any
        // country at all.
        let inUseRegions = inUseRegionNames.size
          ? referenceRegions.filter((name) => inUseRegionNames.has(normalizeRegionName(name)))
          : referenceRegions
        // A deep link (e.g. from Market Analysis's own Import/Export
        // columns) must always be able to land on its own country, even if
        // that country's region has nothing else set up in Commercial
        // Structure yet — the region list is narrowed for tidiness, not to
        // ever block a link the app itself generated.
        if (requested?.region && !inUseRegions.some((name) => normalizeRegionName(name) === normalizeRegionName(requested.region))) {
          inUseRegions = [...inUseRegions, requested.region]
        }

        const initialRegion =
          inUseRegions.find((name) => normalizeRegionName(name) === normalizeRegionName(initialCountry?.region)) ?? inUseRegions[0] ?? ''

        setCountries(tradeData.countries)
        setDefaultYear(tradeData.default_year)
        setRegions(inUseRegions)
        setActiveCountryCodes(activeCodes)
        setRegion(initialRegion)
        setCountry(String(initialCountry?.reporter_code ?? ''))
        // Year is resolved by the probe effect below, not set here — it
        // needs `country` to already be set before it can start.
        setCountriesStatus('ready')
      })
      .catch(() => setCountriesStatus('error'))
    fetchHsProductCatalog()
      .then(setCatalog)
      .catch(() => setCatalog([]))
    // Mount-only: requestedCountry is read once, deliberately, from the URL
    // this page was opened with — it must not re-run every time the page's
    // own controls change the country afterward.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // countriesInRegion: every Comtrade-covered country in the selected
  // region, active-in-Commercial-Structure or not — the region dropdown
  // only narrows which regions are worth looking at, never which
  // countries within one can be picked or queried.
  const countriesInRegion = useMemo(
    () => countries.filter((item) => normalizeRegionName(item.region) === normalizeRegionName(region)),
    [countries, region],
  )

  const handleRegionChange = (newRegion) => {
    setRegion(newRegion)
    const first = countries.find((item) => normalizeRegionName(item.region) === normalizeRegionName(newRegion))
    if (first) setCountry(String(first.reporter_code))
  }

  // The currently selected country's own row from /api/trade/countries —
  // carries its discovered trade_data_source/coverage/note/discovering
  // flag (see backend/trade_sources/discovery.py), independent of which
  // year/flow/drill-down level is on screen.
  const currentCountryData = useMemo(() => countries.find((item) => String(item.reporter_code) === country), [countries, country])

  const updateCountryData = (iso2, patch) => {
    setCountries((prev) => prev.map((item) => (item.iso2 === iso2 ? { ...item, ...patch } : item)))
  }

  // Auto-polls source-status while a discovery/fallback chain is running
  // in the background for the selected country — whether that's from this
  // page's own Re-check button, or (less commonly) a very recent
  // Commercial Structure addition whose one-time discovery hadn't finished
  // yet when this page's country list first loaded.
  useEffect(() => {
    if (!currentCountryData?.discovering || !currentCountryData?.iso2) return undefined
    let cancelled = false
    const iso2 = currentCountryData.iso2

    const poll = async () => {
      while (!cancelled) {
        await new Promise((resolve) => setTimeout(resolve, SOURCE_STATUS_POLL_MS))
        if (cancelled) return
        try {
          const status = await fetchTradeSourceStatus(iso2)
          if (cancelled) return
          if (!status.discovering) {
            updateCountryData(iso2, status)
            return
          }
        } catch {
          return
        }
      }
    }
    poll()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentCountryData?.iso2, currentCountryData?.discovering])

  const handleRecheck = async () => {
    if (!currentCountryData?.iso2 || recheckStatus === 'working') return
    setRecheckStatus('working')
    setRecheckError(null)
    try {
      const result = await recheckTradeSource(currentCountryData.iso2)
      if (result.status === 'comtrade') {
        updateCountryData(currentCountryData.iso2, {
          trade_data_source: 'comtrade',
          trade_data_coverage: 'total',
          trade_data_coverage_note: null,
          discovering: false,
        })
      } else {
        updateCountryData(currentCountryData.iso2, { discovering: true })
      }
    } catch (error) {
      setRecheckError(error.message)
    } finally {
      setRecheckStatus('idle')
    }
  }

  // Picks the year to open a newly selected country on: tries defaultYear
  // (the newest year worth trying) first, then walks backward until one
  // actually has data, since that varies a lot by country — a small
  // territory can be several years behind a larger one. Runs once whenever
  // the country changes (that includes the very first load); it does NOT
  // re-run when the user later flips Imports/Exports, so toggling that
  // never jumps the year selection out from under them — a flow with
  // nothing for the resolved year just shows the normal "no data" state,
  // still just a manual year-pick away.
  useEffect(() => {
    if (!country || !defaultYear) return undefined
    let cancelled = false
    setYear('')
    setResolvingYear(true)
    setSelectedChapter(null)
    setCategories({ status: 'idle', hasData: false, rows: [] })

    const resolve = async () => {
      for (let offset = 0; offset < YEAR_PROBE_ATTEMPTS; offset++) {
        if (cancelled) return
        const candidate = defaultYear - offset
        try {
          const data = await fetchTradeCategories(country, candidate, flow)
          if (data.has_data) {
            if (!cancelled) setYear(String(candidate))
            return
          }
        } catch {
          // Treat a failed probe the same as "nothing reported yet" and
          // keep walking backward rather than surfacing it as an error.
        }
      }
      if (!cancelled) setYear(String(defaultYear - (YEAR_PROBE_ATTEMPTS - 1)))
    }
    resolve().finally(() => !cancelled && setResolvingYear(false))

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country, defaultYear])

  useEffect(() => {
    if (!country || !year) return undefined
    let cancelled = false
    setSelectedChapter(null)
    setCategories({ status: 'loading', hasData: false, rows: [] })
    fetchTradeCategories(country, year, flow)
      .then((data) => {
        if (cancelled) return
        setCategories({ status: 'ready', hasData: data.has_data, rows: data.rows })
      })
      .catch((error) => !cancelled && setCategories({ status: 'error', hasData: false, rows: [], error: error.message }))
    return () => {
      cancelled = true
    }
  }, [country, year, flow])

  useEffect(() => {
    // Deliberately doesn't reset selectedHeading itself (see openChapter,
    // which does that for every route that means "show a chapter's product
    // list from scratch") — a search jump straight to a 6-digit match sets
    // selectedChapter and selectedHeading together in the same handler, and
    // this effect firing on that selectedChapter change must not wipe the
    // heading back out from under it.
    if (!selectedChapter) {
      setProducts({ status: 'idle', hasData: false, rows: [] })
      return undefined
    }
    let cancelled = false
    setProducts({ status: 'loading', hasData: false, rows: [] })
    fetchTradeProducts(country, year, selectedChapter.hs_code, flow)
      .then((data) => {
        if (cancelled) return
        setProducts({ status: 'ready', hasData: data.has_data, rows: data.rows })
      })
      .catch((error) => !cancelled && setProducts({ status: 'error', hasData: false, rows: [], error: error.message }))
    return () => {
      cancelled = true
    }
  }, [country, year, selectedChapter, flow])

  useEffect(() => {
    if (!selectedHeading) {
      setSubheadings({ status: 'idle', hasData: false, rows: [] })
      return undefined
    }
    let cancelled = false
    setSubheadings({ status: 'loading', hasData: false, rows: [] })
    fetchTradeSubheadings(country, year, selectedHeading.hs_code, flow)
      .then((data) => {
        if (cancelled) return
        setSubheadings({ status: 'ready', hasData: data.has_data, rows: data.rows })
      })
      .catch((error) => !cancelled && setSubheadings({ status: 'error', hasData: false, rows: [], error: error.message }))
    return () => {
      cancelled = true
    }
  }, [country, year, selectedHeading, flow])

  // Close the search dropdown on an outside click.
  useEffect(() => {
    const handleClick = (event) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target)) setSearchOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const searchMatches = useMemo(() => {
    const needle = searchTerm.trim().toLowerCase()
    if (needle.length < MIN_SEARCH_CHARS) return []
    return catalog
      .filter((item) => item.description.toLowerCase().includes(needle) || item.hs_code.startsWith(needle))
      .slice(0, MAX_SEARCH_RESULTS)
  }, [catalog, searchTerm])

  const openChapter = (chapterCode, categoryName, highlightCode = null) => {
    setHighlightHsCode(highlightCode)
    setSelectedChapter({ hs_code: chapterCode, category_name: categoryName })
    // Every route through here means "show this chapter's product list from
    // scratch" (a category row click, or a 4-digit search match) — any
    // heading left selected from a previous drill-down must not carry over.
    // A 6-digit search match sets selectedChapter directly instead of going
    // through this function, precisely so it can set its own heading right
    // after without this clearing it back out.
    setSelectedHeading(null)
  }

  const openHeading = (headingCode, headingName, highlightCode = null) => {
    setHighlightHsCode(highlightCode)
    setSelectedHeading({ hs_code: headingCode, description: headingName })
  }

  // categoryNameFor/headingNameFor prefer whatever's already loaded for the
  // current country/year/flow (the real reported name, when it exists)
  // and only fall back to the HS reference's own generic name — used both
  // for a plain row click (already loaded, so this is instant) and for a
  // search jump (which may not have loaded that level yet).
  const categoryNameFor = (chapterCode) =>
    categories.rows.find((row) => row.hs_code === chapterCode)?.category_name ??
    catalog.find((item) => item.level === 4 && item.chapter === chapterCode)?.description ??
    `Chapter ${chapterCode}`

  const headingNameFor = (headingCode) =>
    products.rows.find((row) => row.hs_code === headingCode)?.description ??
    catalog.find((item) => item.level === 4 && item.hs_code === headingCode)?.description ??
    `HS ${headingCode}`

  const handleSelectSearchResult = (item) => {
    if (item.level === 4) {
      openChapter(item.chapter, categoryNameFor(item.chapter), item.hs_code)
    } else {
      // A 6-digit match needs both levels set — the chapter for this
      // heading's own back-navigation, and the heading itself for the
      // subheading view this jump actually opens on.
      setSelectedChapter({ hs_code: item.chapter, category_name: categoryNameFor(item.chapter) })
      openHeading(item.heading, headingNameFor(item.heading), item.hs_code)
    }
    setSearchTerm('')
    setSearchOpen(false)
  }

  const yearOptions = defaultYear ? Array.from({ length: YEARS_BACK + 2 }, (_, index) => defaultYear + 1 - index) : []
  const selectedCountryName = countries.find((item) => String(item.reporter_code) === country)?.name ?? ''
  const flowLabel = flow === 'M' ? 'imports' : 'exports'

  return (
    <section className="global-trade">
      <header className="global-trade__header">
        <h3>Global Trade Data</h3>
        <p>What a country imports or exports, by HS product category — sourced live from UN Comtrade.</p>
      </header>

      {countriesStatus === 'loading' && <EmptyState>Loading countries…</EmptyState>}
      {countriesStatus === 'error' && <EmptyState>Could not load the country list.</EmptyState>}

      {countriesStatus === 'ready' && (
        <>
          <div className="global-trade__controls">
            <label>
              Region
              <select value={region} onChange={(event) => handleRegionChange(event.target.value)}>
                {regions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Country
              <select value={country} onChange={(event) => setCountry(event.target.value)}>
                {countriesInRegion.map((item) => {
                  const isActive = activeCountryCodes.has((item.iso2 || '').toUpperCase())
                  return (
                    <option
                      key={item.reporter_code}
                      value={item.reporter_code}
                      className={isActive ? 'global-trade__option--active' : undefined}
                      style={isActive ? { color: '#35d399', fontWeight: 700 } : undefined}
                    >
                      {item.name}
                    </option>
                  )
                })}
              </select>
            </label>

            <label>
              Year
              <select value={year} onChange={(event) => setYear(event.target.value)}>
                {yearOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <div className="global-trade__flow-toggle" role="group" aria-label="Imports or exports">
              <button type="button" className={flow === 'M' ? 'is-active' : ''} onClick={() => setFlow('M')}>
                Imports
              </button>
              <button type="button" className={flow === 'X' ? 'is-active' : ''} onClick={() => setFlow('X')}>
                Exports
              </button>
            </div>

            <div className="global-trade__search" ref={searchBoxRef}>
              <label>
                Jump to a product
                <input
                  type="text"
                  value={searchTerm}
                  placeholder="e.g. tomatoes"
                  onChange={(event) => {
                    setSearchTerm(event.target.value)
                    setSearchOpen(true)
                  }}
                  onFocus={() => setSearchOpen(true)}
                />
              </label>
              {searchOpen && searchTerm.trim().length >= MIN_SEARCH_CHARS && (
                <ul className="global-trade__search-results">
                  {searchMatches.length === 0 ? (
                    <li className="global-trade__search-empty">No matching product.</li>
                  ) : (
                    searchMatches.map((item) => (
                      <li key={item.hs_code}>
                        <button type="button" onClick={() => handleSelectSearchResult(item)}>
                          <span className="global-trade__search-level">HS{item.level}</span>
                          <span className="global-trade__code">{item.hs_code}</span>
                          <span>{item.description}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
          </div>
          <p className="global-trade__region-hint">
            <strong>Green</strong> countries are already set up in Commercial Structure — every other country in the region can
            still be selected and queried the same way.
          </p>

          <div className="global-trade__source-row">
            <span className="global-trade__source-label">
              Data source: <strong>{tradeSourceLabel(currentCountryData?.trade_data_source)}</strong>
              {currentCountryData?.discovering && ' — checking…'}
            </span>
            <button
              type="button"
              className="global-trade__recheck"
              onClick={handleRecheck}
              disabled={!currentCountryData?.iso2 || recheckStatus === 'working' || currentCountryData?.discovering}
            >
              {currentCountryData?.discovering ? 'Checking…' : recheckStatus === 'working' ? 'Starting…' : 'Re-check'}
            </button>
            {recheckError && <span className="global-trade__source-error">{recheckError}</span>}
          </div>

          {!selectedChapter && (
            <div className="global-trade__panel">
              <h4>
                {selectedCountryName} — {flowLabel} by category{year ? `, ${year}` : ''}
              </h4>
              {currentCountryData?.trade_data_coverage === 'bilateral' && (
                <BilateralCoverageBanner note={currentCountryData?.trade_data_coverage_note} />
              )}

              {resolvingYear && <EmptyState>Finding the most recent year with reported data…</EmptyState>}
              {!resolvingYear && categories.status === 'loading' && <EmptyState>Loading…</EmptyState>}
              {!resolvingYear && categories.status === 'error' && <EmptyState>{categories.error}</EmptyState>}
              {categories.status === 'ready' && !categories.hasData && (
                <EmptyState>
                  No data reported for {selectedCountryName} in {year}. Smaller territories often report late or not
                  at all for a given year — try an earlier year.
                </EmptyState>
              )}
              {categories.status === 'ready' && categories.hasData && (
                <div className="global-trade__table-wrap">
                  <table className="global-trade__table">
                    <thead>
                      <tr>
                        <th>HS</th>
                        <th>Category</th>
                        <th className="global-trade__value-head">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {categories.rows.map((row) => (
                        <tr key={row.hs_code} onClick={() => openChapter(row.hs_code, row.category_name)}>
                          <td className="global-trade__code">{row.hs_code}</td>
                          <td>{row.category_name}</td>
                          <td className="global-trade__value">{formatValue(row.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {selectedChapter && !selectedHeading && (
            <div className="global-trade__panel">
              <div className="global-trade__panel-head">
                <button
                  type="button"
                  className="global-trade__back"
                  onClick={() => {
                    setSelectedChapter(null)
                    setSelectedHeading(null)
                  }}
                >
                  ← Back to categories
                </button>
                <h4>
                  {selectedChapter.category_name} (HS {selectedChapter.hs_code}) — {flowLabel} product detail, {year}
                </h4>
              </div>
              {currentCountryData?.trade_data_coverage === 'bilateral' && (
                <BilateralCoverageBanner note={currentCountryData?.trade_data_coverage_note} />
              )}

              {products.status === 'loading' && <EmptyState>Loading…</EmptyState>}
              {products.status === 'error' && <EmptyState>{products.error}</EmptyState>}
              {products.status === 'ready' && !products.hasData && (
                <EmptyState>No product-level data reported for this chapter.</EmptyState>
              )}
              {products.status === 'ready' && products.hasData && (
                <div className="global-trade__table-wrap">
                  <table className="global-trade__table">
                    <thead>
                      <tr>
                        <th>HS</th>
                        <th>Product</th>
                        <th className="global-trade__value-head">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {products.rows.map((row) => (
                        <tr
                          key={row.hs_code}
                          className={row.hs_code === highlightHsCode ? 'is-highlighted' : ''}
                          onClick={() => openHeading(row.hs_code, row.description)}
                        >
                          <td className="global-trade__code">{row.hs_code}</td>
                          <td>{row.description}</td>
                          <td className="global-trade__value">{formatValue(row.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {selectedChapter && selectedHeading && (
            <div className="global-trade__panel">
              <div className="global-trade__panel-head">
                <button type="button" className="global-trade__back" onClick={() => setSelectedHeading(null)}>
                  ← Back to products
                </button>
                <h4>
                  {selectedHeading.description} (HS {selectedHeading.hs_code}) — {flowLabel} subheading detail, {year}
                </h4>
              </div>
              {currentCountryData?.trade_data_coverage === 'bilateral' && (
                <BilateralCoverageBanner note={currentCountryData?.trade_data_coverage_note} />
              )}

              {subheadings.status === 'loading' && <EmptyState>Loading…</EmptyState>}
              {subheadings.status === 'error' && <EmptyState>{subheadings.error}</EmptyState>}
              {subheadings.status === 'ready' && !subheadings.hasData && (
                <EmptyState>No subheading-level data reported for this product.</EmptyState>
              )}
              {subheadings.status === 'ready' && subheadings.hasData && (
                <div className="global-trade__table-wrap">
                  <table className="global-trade__table">
                    <thead>
                      <tr>
                        <th>HS</th>
                        <th>Subheading</th>
                        <th className="global-trade__value-head">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {subheadings.rows.map((row) => (
                        <tr key={row.hs_code} className={row.hs_code === highlightHsCode ? 'is-highlighted' : ''}>
                          <td className="global-trade__code">{row.hs_code}</td>
                          <td>{row.description}</td>
                          <td className="global-trade__value">{formatValue(row.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}

export default GlobalTradeDataView
