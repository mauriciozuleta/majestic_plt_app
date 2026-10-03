// Global Trade Data module — UN Comtrade import/export figures, proxied
// through our own backend (backend/routers/comtrade.py) so the Comtrade
// subscription key never reaches the browser. These calls carry no key of
// their own; the backend attaches it server-side and caches the result.

import { API_BASE } from './apiBase'

async function request(path, params) {
  const query = new URLSearchParams(params)
  const response = await fetch(`${API_BASE}${path}?${query.toString()}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

// { countries: [{ name, reporter_code, iso3 }], default_year }
export const fetchTradeCountries = () => request('/api/trade/countries', {})

// [{ hs_code, level: 4 | 6, chapter, heading, description }] for every HS
// 4-digit heading and 6-digit subheading Comtrade knows about — the
// product-search catalog. `level` says which drill-down view a match
// opens. Meant to be fetched once and cached client-side (see
// GlobalTradeDataView), not re-requested per keystroke: it never touches
// Comtrade's quota-limited data API itself.
export const fetchHsProductCatalog = () => request('/api/trade/hs-products', {}).then((data) => data.products)

// { country, year, flow, has_data, rows: [{ hs_code, category_name, value }] } — HS 2-digit chapters, sorted by value.
export const fetchTradeCategories = (country, year, flow) => request('/api/trade/categories', { country, year, flow })

// { country, year, chapter, flow, has_data, rows: [{ hs_code, description, value }] } — HS 4-digit products within one chapter.
export const fetchTradeProducts = (country, year, chapter, flow) =>
  request('/api/trade/products', { country, year, chapter, flow })

// { country, year, heading, flow, has_data, rows: [{ hs_code, description, value }] } — HS 6-digit subheadings within one 4-digit heading. The final drill-down level.
export const fetchTradeSubheadings = (country, year, heading, flow) =>
  request('/api/trade/subheadings', { country, year, heading, flow })

// SAM Overview (Market Analysis ▸ Market Size ▸ SAM ▸ Overview): for every
// region in the portfolio, the real Comtrade 2-digit chapter import total
// for each of the given qualifying (green) chapters, summed only across
// that region's countries that actually reported it — see
// backend/routers/comtrade.py's sam_overview for the exclusion/bilateral
// rules. `chapters` is an array of 2-digit HS chapter codes (the frontend's
// own buildCategoryCoverage() output — see productPortfolio.js).
//
// PERSISTED as of this pass: once computed once, this instantly returns the
// stored result (`computed_at` included) instead of re-aggregating live —
// `chapters` passed here is ignored once a stored snapshot exists. Ask the
// chatbox to "refresh SAM" to force a real recompute (see
// backend/routers/assistant.py's refresh_market_size tool).
// -> { flow, default_year, regions: [{ region, categories: [{ chapter, value, bilateral, countries: [{ id, name, country_code, value, bilateral, year }] }] }], computed_at }
export const fetchSamOverview = (chapters) => request('/api/trade/sam-overview', { chapters: chapters.join(',') })

// Product-level SAM: each 6-digit HS code's imports for every active country
// of one region (backend/routers/comtrade.py's product_sam).
// -> { region, flow, countries: [{ name, year, status, error? }],
//      products: { [hs6]: { region_total, countries: { [name]: { value, year } } } } }
export const fetchProductSam = (region, hsCodes) => request('/api/trade/product-sam', { region, hs_codes: hsCodes.join(',') })

// Home page's SAM card: the stored snapshot's grand total across every
// region/category + how many qualifying categories contributed — a plain
// DB read, never live Comtrade work, so Home stays instant even if SAM has
// never been computed (comes back with total_value 0 / computed_at null).
// -> { computed_at, total_value, category_count }
export const fetchSamOverviewSummary = () => request('/api/trade/sam-overview/summary', {})

// SAM Overview's opt-in estimation layer (see SamPanel.jsx's "Include
// estimated values (modeled)" toggle and MARKET_SIZING_METHODOLOGY.md) —
// only called when that toggle is switched on, never on the default
// Overview load. Per qualifying chapter, per region: either a fitted
// population + GDP-per-capita regression (see backend/estimation/
// regression.py) applied to every country with NO existing confirmed/
// bilateral row at all for that chapter, or, below the minimum confirmed-
// country sample, an explanatory status in place of a model.
// -> { flow, default_year, min_sample_size, low_confidence_r2_threshold,
//      regions: [{ region, categories: [{ chapter, status: 'estimated' |
//      'insufficient_confirmed_data', message, sample_size, min_sample_size,
//      model: null | { method, r_squared, low_confidence, sample_size,
//      trained_countries: [{ id, name, country_code, value, year }] },
//      estimates: [{ id, name, country_code, predicted_value, low_confidence,
//      population, population_year, gdp_per_capita, gdp_per_capita_year }],
//      unavailable: [{ id, name, country_code, reason }] }] }] }
export const fetchSamOverviewEstimates = (chapters) =>
  request('/api/trade/sam-overview-estimates', { chapters: chapters.join(',') })

// TAM ▸ Overview (Market Analysis ▸ Market Size ▸ TAM ▸ Overview): real,
// UNSCOPED global UN Comtrade import totals — one figure per qualifying
// chapter, summed across every country that reported it worldwide, not
// just this app's tracked Commercial Structure countries (that narrower
// figure is SAM, above). See backend/routers/comtrade.py's
// tam_global_overview and MARKET_SIZING_METHODOLOGY.md Part 2 for the full
// mechanism (reporterCode omitted, not 0 — there is no "World" reporter)
// and the duplicate-row guard (motCode/partner2Code/customsCode all
// pinned to their "total" values in backend/comtrade/client.py's
// _TOTALS_ONLY). `chapters` is the same qualifying (green) chapter list
// SAM uses — see buildCategoryCoverage(), productPortfolio.js.
// PERSISTED as of this pass, same contract as fetchSamOverview above: once
// computed once, this instantly returns the stored result (`computed_at`
// included) instead of re-aggregating live. Ask the chatbox to "refresh
// TAM" to force a real recompute.
// -> { flow, default_year, categories: [{ chapter, year, value,
//      country_count, countries: [{ reporter_code, name, value }] }], computed_at }
export const fetchTamGlobalOverview = (chapters) =>
  request('/api/trade/tam-global-overview', { chapters: chapters.join(',') })

// Home page's TAM card: the stored snapshot's grand total across every
// qualifying category + how many categories contributed — same
// Comtrade-free, DB-only contract as fetchSamOverviewSummary above.
// -> { computed_at, total_value, category_count }
export const fetchTamGlobalOverviewSummary = () => request('/api/trade/tam-global-overview/summary', {})

// Source-discovery status for one country (backend/trade_sources/) —
// { country_code, trade_data_source, trade_data_coverage, trade_data_coverage_note, trade_data_source_checked_at, discovering, error }.
// Polled by GlobalTradeDataView while a re-check's fallback chain is
// running in the background.
export const fetchTradeSourceStatus = (countryCode) => request(`/api/trade/countries/${countryCode}/source-status`, {})

// Unconditionally re-runs the full discovery chain for one country
// (Comtrade check, then the fallback chain if that's empty), overwriting
// its stored source. Returns { status: 'comtrade' | 'discovering', ... }
// immediately — the fallback chain (when it runs) finishes in the
// background; poll fetchTradeSourceStatus until `discovering` is false.
export async function recheckTradeSource(countryCode) {
  const response = await fetch(`${API_BASE}/api/trade/countries/${countryCode}/recheck-source`, { method: 'POST' })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
