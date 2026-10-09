import { API_BASE } from './apiBase'

// Global Tourism & Economic Dependency — backend/routers/tourism.py (our own API; the providers are called by the server only).

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    throw new Error((typeof detail === 'string' ? detail : detail?.message) || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const yearParam = (year) => (year === 'latest' || year == null ? 'latest' : String(year))

// -> { countries: [{ country_id, country_name, iso_alpha2, iso_alpha3, region, territory_status, parent_country, coverage: { world_bank, wttc, idb, statista } }], regions }
export const fetchTourismCountries = ({ q, region, status } = {}) => {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (region) params.set('region', region)
  if (status) params.set('status', status)
  return request(`/tourism/countries?${params.toString()}`)
}

export const addTourismCountry = (payload) => request('/tourism/countries', json('POST', payload))

// -> { year, rows: [{ country_id, country, iso_alpha2, iso_alpha3, region, territory_status, indicators: { CODE: { value, unit, year, source, dataset, edition, url, status, note, reason } } }], warnings, unknown }
export const fetchTourismCompare = (codes, year, refresh = false) =>
  request(`/tourism/compare?countries=${encodeURIComponent(codes.join(','))}&year=${yearParam(year)}${refresh ? '&refresh=true' : ''}`)

// -> { row, warnings, observations: [...] }
export const fetchTourismCountry = (code, year) => request(`/tourism/countries/${encodeURIComponent(code)}?year=${yearParam(year)}`)

// -> { country, series: { CODE: [{ year, value, source, status }] }, warnings }
export const fetchTourismHistory = (code, from, to) => {
  const params = new URLSearchParams({ country: code })
  if (from) params.set('from', String(from))
  if (to) params.set('to', String(to))
  return request(`/tourism/history?${params.toString()}`)
}

export const fetchTourismProviders = (check = false) => request(`/tourism/providers/status${check ? '?check=true' : ''}`)
export const setTourismProviderEnabled = (id, enabled) => request(`/tourism/providers/${id}`, json('PUT', { enabled }))
export const syncTourismProvider = (id) => request(`/tourism/providers/${id}/sync`, { method: 'POST' })
export const importTourismFile = (payload) => request('/tourism/import', json('POST', payload))
export const fetchTourismImports = () => request('/tourism/imports')

export const tourismExportUrl = ({ codes, year, format, layout, from, to }) => {
  const params = new URLSearchParams({ countries: codes.join(','), year: yearParam(year), format, layout })
  if (from) params.set('from', String(from))
  if (to) params.set('to', String(to))
  return `${API_BASE}/tourism/export?${params.toString()}`
}
