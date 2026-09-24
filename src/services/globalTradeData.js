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
