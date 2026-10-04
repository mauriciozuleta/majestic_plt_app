import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { IconCheck } from '@tabler/icons-react'
import { fetchCountryProfile, fetchMarketAnalysisRegions } from '../../services/commercialStructure'
import { fetchTradeCountries } from '../../services/globalTradeData'
import { buildMarketAnalysisStatus } from '../../services/marketAnalysisStatus'
import { exportCountryProfileToPdf } from '../company/tabs/OperationsTab/countryProfileExport'
import MarketAnalysisPanel from '../company/tabs/OperationsTab/MarketAnalysis/MarketAnalysisPanel'
import AvailableCategoriesPanel from './AvailableCategoriesPanel'
import SamPanel from './SamPanel'
import GlobalTamPanel from './GlobalTamPanel'
import MarketOpportunitiesPanel from './MarketOpportunitiesPanel'
import SpeciesGalleryPanel from './SpeciesGalleryPanel'
import { useAppStore } from '../../store/useAppStore'
import './MarketAnalysisView.css'

// The whole page's own top-level tabs — general, not per-country. Country
// Information holds everything this page always showed (the region/country
// status table below, and the per-country detail panel it opens into);
// Market Size groups Available Categories and the TAM/SAM/SOM tiers as its
// own nested tabs (see MARKET_SIZE_TABS below). Each tab gets its own
// tinted background (low-alpha, never a full solid fill) so they're
// distinguishable at a glance even before their content exists to tell
// them apart by.
const PAGE_TABS = [
  { key: 'country-information', label: 'Country Information', rgb: '59, 130, 246', text: '#93c5fd' },
  { key: 'market-size', label: 'Market Size', rgb: '167, 139, 250', text: '#e9d5ff' },
  { key: 'market-opportunities', label: 'Market Opportunities', rgb: '20, 184, 166', text: '#5eead4' },
  { key: 'variety-gallery', label: 'Variety Gallery', rgb: '236, 72, 153', text: '#f9a8d4' },
]

// Nested tabs shown inside the Market Size page tab — same tinted-background
// style, one level down. Available Categories comes first, beside TAM.
const MARKET_SIZE_TABS = [
  { key: 'available-categories', label: 'Available Categories', rgb: '53, 211, 153', text: '#6ee7b7' },
  { key: 'tam', label: 'TAM', rgb: '167, 139, 250', text: '#e9d5ff' },
  { key: 'sam', label: 'SAM', rgb: '251, 191, 36', text: '#fde68a' },
  { key: 'som', label: 'SOM', rgb: '53, 211, 153', text: '#6ee7b7' },
]

// One column per pill a country's analysis can have. `tabKey` is where the
// detail panel below (MarketAnalysisPanel — just "Overview" and "Country
// Product Portfolio" now, no second pill layer) jumps to when a country
// hasn't got this one yet, so the table doubles as a way to go build it,
// not just a report of what already exists.
const COLUMNS = [
  { key: 'profile', label: 'Commercial Profile', group: 'Overview', tabKey: 'overview' },
  { key: 'product', label: 'Country Product Portfolio', group: 'Country Product Portfolio', tabKey: 'products' },
  // Global Trade Data isn't a document to build or a tab inside this
  // country's own panel — it's UN Comtrade figures, a separate global
  // module (see components/globalTradeData). These two link out to it,
  // pre-filtered to this country and the matching flow, instead of opening
  // anything in the detail panel below.
  { key: 'comtradeImport', label: 'Import', group: 'Global Trade Data', flow: 'M' },
  { key: 'comtradeExport', label: 'Export', group: 'Global Trade Data', flow: 'X' },
]
// Consecutive columns sharing a group get one merged header cell — computed
// once since COLUMNS is static.
const GROUPS = COLUMNS.reduce((groups, column) => {
  const last = groups[groups.length - 1]
  if (last && last.label === column.group) last.span += 1
  else groups.push({ label: column.group, span: 1 })
  return groups
}, [])

// Each group and each individual pill column gets its own header color —
// purely a visual reference so a column is easy to find at a glance across
// a wide, scrolling table; the body cells stay green/muted for done/pending
// regardless of column, so that signal is never diluted by this.
const GROUP_COLOR = { Overview: 'overview', 'Country Product Portfolio': 'product', 'Global Trade Data': 'trade' }
const COLUMN_COLOR = {
  profile: 'profile',
  product: 'product',
  comtradeImport: 'comtrade-import',
  comtradeExport: 'comtrade-export',
}

function formatWhen(iso) {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { dateStyle: 'medium' })
}

// Same fixed markdown shape every generated report uses (headings,
// paragraphs, list items) — not a general-purpose Markdown renderer.
function MarkdownBody({ markdown }) {
  const lines = markdown.split('\n')
  const elements = []
  let paragraph = []
  let key = 0
  const flush = () => {
    if (paragraph.length) {
      elements.push(<p key={key++}>{paragraph.join(' ')}</p>)
      paragraph = []
    }
  }
  lines.forEach((rawLine) => {
    const line = rawLine.trim()
    if (!line) return flush()
    if (line.startsWith('# ')) {
      flush()
      elements.push(<h1 key={key++}>{line.slice(2)}</h1>)
    } else if (line.startsWith('## ')) {
      flush()
      elements.push(<h2 key={key++}>{line.slice(3)}</h2>)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      flush()
      elements.push(<li key={key++}>{line.slice(2)}</li>)
    } else {
      paragraph.push(line)
    }
  })
  flush()
  return <div className="country-profile-view__body">{elements}</div>
}

function DocCell({ done, label, count, onClick }) {
  return (
    <button type="button" className={`market-analysis__pill ${done ? 'is-done' : 'is-pending'}`} onClick={onClick} title={label}>
      {done ? (
        <>
          <IconCheck size={13} stroke={2.5} />
          {count > 1 ? `×${count}` : 'View'}
        </>
      ) : (
        '—'
      )}
    </button>
  )
}

// Market Analysis as its own module: every region we operate in, its active
// countries (the ones set up in Commercial Structure) as rows, and one
// column per report/analysis a country can have. A green check is a built
// document — click it to open the document itself, right from the table.
// An empty cell jumps to that section below instead, to go build it. Any
// build completing anywhere on this page refreshes every check live (see
// `onBuilt` below) — reopening the page (or the sidebar link) picks up a
// newly added country the same way, since regions are re-fetched on mount.
function MarketAnalysisView() {
  const { countryId } = useParams()
  const navigate = useNavigate()
  const companies = useAppStore((state) => state.companies)
  const currentUser = useAppStore((state) => state.currentUser)

  // ?tab=market-opportunities (e.g. from the Shipment builder) opens that tab.
  const [searchParams] = useSearchParams()
  const [pageTab, setPageTab] = useState(() => searchParams.get('tab') || 'country-information')
  const [marketSizeTab, setMarketSizeTab] = useState('available-categories')
  const [regions, setRegions] = useState([])
  const [status, setStatus] = useState({})
  const [loadStatus, setLoadStatus] = useState('loading')
  const [initialRequest, setInitialRequest] = useState(null)
  const [viewingDoc, setViewingDoc] = useState(null)
  const [exportingPdf, setExportingPdf] = useState(false)
  // Countries UN Comtrade has a verified reporter code for (see
  // backend/comtrade/countries.py) — matched by name against this page's
  // own countries to decide whether the Global Trade Data columns link out
  // or show as not available. Fetched once; it's a short, static list.
  const [tradeCountryCodes, setTradeCountryCodes] = useState({})
  const detailRef = useRef(null)

  useEffect(() => {
    fetchTradeCountries()
      .then((data) => {
        const byName = {}
        data.countries.forEach((item) => {
          byName[item.name.trim().toLowerCase()] = item.reporter_code
        })
        setTradeCountryCodes(byName)
      })
      .catch(() => setTradeCountryCodes({}))
  }, [])

  const countries = regions.flatMap((region) => region.countries.map((country) => ({ ...country, region: region.region })))
  const countryById = new Map(countries.map((country) => [country.id, country]))
  const selected = countryId ? countryById.get(countryId) : null
  // ISO2 -> this country's own Commercial Structure row (id/company_id),
  // for Available Categories' country-code links: buildCategoryCoverage()
  // tags coverage with ISO2 codes from the global reference-countries list
  // (see productPortfolio.js), which has no .id/.company_id of its own —
  // this page's own `countries` (fetchMarketAnalysisRegions) does, so this
  // is the map that turns a clicked ISO2 code back into a routable country.
  const countryByIso2 = new Map()
  countries.forEach((country) => {
    if (country.country_code) countryByIso2.set(country.country_code.toUpperCase(), country)
  })

  const loadRegions = useCallback(() => {
    setLoadStatus('loading')
    return fetchMarketAnalysisRegions()
      .then((rows) => {
        setRegions(rows)
        setLoadStatus('ready')
        return rows.flatMap((region) => region.countries)
      })
      .catch(() => {
        setLoadStatus('error')
        return []
      })
  }, [])

  const refreshStatus = useCallback((countryList) => {
    if (!countryList.length) {
      setStatus({})
      return
    }
    buildMarketAnalysisStatus(countryList).then(setStatus)
  }, [])

  useEffect(() => {
    loadRegions().then(refreshStatus)
  }, [loadRegions, refreshStatus])

  const selectCountry = (country) => {
    setInitialRequest(null)
    navigate(country.id === countryId ? '/market-analysis' : `/market-analysis/${country.id}`)
  }

  // `extra` lets a caller attach more than just which pill to open (e.g.
  // Available Categories' country-code click also needs to say which HS
  // code to land on — see focusCategoryProduct below); every existing
  // caller just wants the pill, so extra defaults to nothing.
  const focusPanel = (country, tabKey, extra = {}) => {
    setInitialRequest({ countryId: country.id, tabKey, ...extra })
    if (country.id !== countryId) navigate(`/market-analysis/${country.id}`)
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  // Available Categories' own "jump to this product" — a country-code
  // click there carries the ISO2 code it was shown under (now always the
  // deepest HS level that product actually reached, see
  // buildCategoryCoverage) and that level's own HS code. Available
  // Categories lives under the separate Market Size page tab, so this also
  // flips back to Country Information before focusing the country panel.
  const focusCategoryProduct = (iso2, hsCode) => {
    const country = countryByIso2.get((iso2 || '').toUpperCase())
    if (!country) return
    setPageTab('country-information')
    focusPanel(country, 'products', { hsCode })
  }

  const openProfile = async (country) => {
    const data = await fetchCountryProfile(country.company_id, country.id)
    if (data.exists) setViewingDoc({ title: `${country.name} — Commercial Profile`, content: data.content, generatedAt: data.generated_at })
  }

  const handleExportPdf = async () => {
    if (!viewingDoc || exportingPdf) return
    setExportingPdf(true)
    try {
      const company = companies.find((item) => item.id === selected?.company_id)
      await exportCountryProfileToPdf(
        viewingDoc.content,
        { company, title: viewingDoc.title, exportedBy: currentUser?.name },
        `${viewingDoc.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.pdf`,
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingPdf(false)
    }
  }

  const onBuilt = () => refreshStatus(countries)
  const hasCountries = countries.length > 0

  return (
    <section className="market-analysis">
      <header className="market-analysis__header">
        <h3>Market Analysis</h3>
        <p>Every region we operate in, its active countries, and what's been built for each. A check opens the document; an empty cell takes you to build it.</p>
      </header>

      <div className="market-analysis__tab-bar">
        {PAGE_TABS.map((tab) => {
          const isActive = pageTab === tab.key
          return (
            <button
              key={tab.key}
              type="button"
              className={`market-analysis__tab ${isActive ? 'is-active' : ''}`}
              onClick={() => setPageTab(tab.key)}
              style={{
                background: `rgba(${tab.rgb}, ${isActive ? 0.28 : 0.14})`,
                color: isActive ? tab.text : undefined,
                borderBottomColor: isActive ? `rgba(${tab.rgb}, 0.28)` : undefined,
              }}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {pageTab === 'market-size' && (
        <div className="market-analysis__tab-panel">
          <div className="market-analysis__tab-bar market-analysis__tab-bar--nested">
            {MARKET_SIZE_TABS.map((tab) => {
              const isActive = marketSizeTab === tab.key
              return (
                <button
                  key={tab.key}
                  type="button"
                  className={`market-analysis__tab ${isActive ? 'is-active' : ''}`}
                  onClick={() => setMarketSizeTab(tab.key)}
                  style={{
                    background: `rgba(${tab.rgb}, ${isActive ? 0.28 : 0.14})`,
                    color: isActive ? tab.text : undefined,
                    borderBottomColor: isActive ? `rgba(${tab.rgb}, 0.28)` : undefined,
                  }}
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
          <div className="market-analysis__tab-panel market-analysis__tab-panel--nested">
            {marketSizeTab === 'available-categories' && <AvailableCategoriesPanel onCountryCodeClick={focusCategoryProduct} />}
            {marketSizeTab === 'tam' && <GlobalTamPanel />}
            {marketSizeTab === 'sam' && <SamPanel />}
            {marketSizeTab === 'som' && <p className="market-analysis__hint">SOM (Serviceable Obtainable Market) is coming soon.</p>}
          </div>
        </div>
      )}

      {pageTab === 'market-opportunities' && (
        <div className="market-analysis__tab-panel">
          <MarketOpportunitiesPanel />
        </div>
      )}

      {pageTab === 'variety-gallery' && (
        <div className="market-analysis__tab-panel">
          <SpeciesGalleryPanel />
        </div>
      )}

      {pageTab === 'country-information' && (
        <div className="market-analysis__tab-panel">
        {loadStatus === 'loading' && <p className="market-analysis__hint">Loading regions…</p>}
        {loadStatus === 'error' && <p className="market-analysis__hint">Could not load the regions.</p>}
        {loadStatus === 'ready' && regions.length === 0 && (
          <p className="market-analysis__hint">No regions yet — assign one to a company in Commercial Structure first.</p>
        )}
        {loadStatus === 'ready' && regions.length > 0 && !hasCountries && (
          <p className="market-analysis__hint">No active countries yet — activate countries in Commercial Structure.</p>
        )}

        {regions.length > 0 && (
          // One table for every region, not one per card: a single shared
          // header (never repeated) and a single horizontal scrollbar for the
          // whole thing. Each region is a full-width divider row inside the
          // same table, so its columns line up with every other region's —
          // a fixed table layout (see the CSS) is what keeps every "View"/"—"
          // column the same width regardless of what's in it.
          <div className="market-analysis__table-wrap">
            <table className="market-analysis__table">
              <colgroup>
                <col className="market-analysis__col-country" />
                <col className="market-analysis__col-company" />
                {COLUMNS.map((column) => (
                  <col key={column.key} className="market-analysis__col-pill" />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th rowSpan={2}>Country</th>
                  <th rowSpan={2}>Company</th>
                  {GROUPS.map((group) => (
                    <th
                      key={group.label}
                      colSpan={group.span}
                      className={`market-analysis__group-head market-analysis__group-head--${GROUP_COLOR[group.label]}`}
                    >
                      {group.label}
                    </th>
                  ))}
                </tr>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.key} className={`market-analysis__pill-head market-analysis__pill-head--${COLUMN_COLOR[column.key]}`}>
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {regions.map((region) => (
                  <Fragment key={region.region}>
                    <tr className="market-analysis__region-row">
                      <td colSpan={2 + COLUMNS.length}>
                        <span className="market-analysis__region-name">{region.region}</span>
                        <span className="market-analysis__region-count">
                          {region.countries.length} active {region.countries.length === 1 ? 'country' : 'countries'}
                        </span>
                      </td>
                    </tr>
                    {region.countries.length === 0 ? (
                      <tr>
                        <td colSpan={2 + COLUMNS.length} className="market-analysis__empty-row">
                          No active countries in this region yet.
                        </td>
                      </tr>
                    ) : (
                      region.countries.map((country) => {
                        const rowStatus = status[country.id]
                        return (
                          <tr key={country.id} className={country.id === countryId ? 'is-selected' : ''}>
                            <td>
                              <button type="button" className="market-analysis__country-link" onClick={() => selectCountry(country)}>
                                {country.name}
                              </button>
                            </td>
                            <td className="market-analysis__company">{country.company_name}</td>
                            {COLUMNS.map((column) => {
                              // Independent of rowStatus (built documents) —
                              // whether Comtrade covers this country at all is
                              // known as soon as the trade-country list loads.
                              if (column.flow) {
                                const reporterCode = tradeCountryCodes[country.name.trim().toLowerCase()]
                                return (
                                  <td key={column.key} className="market-analysis__pill-cell">
                                    <DocCell
                                      done={reporterCode != null}
                                      label={`UN Comtrade ${column.flow === 'M' ? 'imports' : 'exports'}`}
                                      onClick={() =>
                                        reporterCode != null &&
                                        navigate(`/global-trade-data?country=${reporterCode}&flow=${column.flow}`)
                                      }
                                    />
                                  </td>
                                )
                              }
                              if (!rowStatus) return <td key={column.key} className="market-analysis__pill-cell" />
                              if (column.key === 'profile') {
                                return (
                                  <td key={column.key} className="market-analysis__pill-cell">
                                    <DocCell
                                      done={!!rowStatus.profile}
                                      label="Commercial Profile"
                                      onClick={() => (rowStatus.profile ? openProfile(country) : focusPanel(country, column.tabKey))}
                                    />
                                  </td>
                                )
                              }
                              if (column.key === 'product') {
                                return (
                                  <td key={column.key} className="market-analysis__pill-cell">
                                    <DocCell
                                      done={rowStatus.hasProductData}
                                      label="Country Product Portfolio"
                                      onClick={() => focusPanel(country, column.tabKey)}
                                    />
                                  </td>
                                )
                              }
                              return (
                                <td key={column.key} className="market-analysis__pill-cell">
                                  <DocCell done={false} label={column.label} onClick={() => focusPanel(country, column.tabKey)} />
                                </td>
                              )
                            })}
                          </tr>
                        )
                      })
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selected && (
          <div className="market-analysis__detail" ref={detailRef}>
            <div className="market-analysis__detail-head">
              <h4>{selected.name}</h4>
              <span>
                {selected.region} · {selected.company_name}
              </span>
            </div>
            <MarketAnalysisPanel
              // Keyed on the requested tab (and HS code, when a country-code
              // click from Available Categories asked for one) too, not just
              // the country, so clicking a different pending column — or a
              // different leaf-level country code — for the same already-
              // selected country still jumps/filters there (a plain
              // key={selected.id} wouldn't remount, and the panel's own tab
              // state only reads its initial props once).
              key={`${selected.id}:${initialRequest?.countryId === selected.id ? initialRequest.tabKey : ''}:${initialRequest?.countryId === selected.id ? initialRequest.hsCode || '' : ''}`}
              companyId={selected.company_id}
              country={selected}
              initialTabKey={initialRequest?.countryId === selected.id ? initialRequest.tabKey : null}
              initialHsCode={initialRequest?.countryId === selected.id ? initialRequest.hsCode || null : null}
              onBuilt={onBuilt}
            />
          </div>
        )}
        {loadStatus === 'ready' && countryId && !selected && <p className="market-analysis__hint">That country is no longer active.</p>}

        {viewingDoc && (
          <div className="country-profile-view__overlay">
            <div className="country-profile-view">
              <header className="country-profile-view__header">
                <div>
                  <h3>{viewingDoc.title}</h3>
                  {viewingDoc.generatedAt && (
                    <span className="country-profile-view__meta">Generated {formatWhen(viewingDoc.generatedAt)}</span>
                  )}
                </div>
                <div className="country-profile-view__actions">
                  <button type="button" onClick={handleExportPdf} disabled={exportingPdf}>
                    {exportingPdf ? 'Exporting…' : 'Export PDF'}
                  </button>
                  <button type="button" className="country-profile-view__close" onClick={() => setViewingDoc(null)}>
                    Close
                  </button>
                </div>
              </header>
              <div className="country-profile-view__scroll">
                <MarkdownBody markdown={viewingDoc.content} />
              </div>
            </div>
          </div>
        )}
        </div>
      )}
    </section>
  )
}

export default MarketAnalysisView
