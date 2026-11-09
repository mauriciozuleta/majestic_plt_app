// API of the aviation fuel price module (backend/fuel_prices/, routes in backend/routers/fuel_prices.py). Prices are USD per US gallon.
import { API_BASE } from './apiBase'

const BASE = `${API_BASE}/api/fuel`

async function request(path, options) {
  const response = await fetch(`${BASE}${path}`, options)
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.errors?.join('; ') || `Request failed (${response.status})`)
  }
  return body
}

const qs = (params) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

const post = (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const searchFuelPlaces = (q) => request(`/search${qs({ q })}`)
export const fetchFuelPrice = ({ country, airport, operatorClass }) => request(`/price${qs({ country, airport, class: operatorClass })}`)
export const fetchFuelSeries = ({ country, airport, region, operatorClass, kind, driver, from }) =>
  request(`/series${qs({ country, airport, region, class: operatorClass, kind, driver, from })}`)
export const fetchFuelStat = (kind, { country, airport, operatorClass, from, to }) => request(`/stats/${kind}${qs({ country, airport, class: operatorClass, from, to })}`)
export const fetchFuelSources = () => request('/sources')
export const setFuelSourceEnabled = (id, enabled, signedOffBy) => post(`/sources/${id}/enable`, { enabled, signed_off_by: signedOffBy })
export const refreshFuelSource = (id, full = false) => post(`/sources/${id}/refresh${qs({ full })}`, {})
export const fetchFuelCoverage = () => request('/coverage')
export const fetchFuelEvents = () => request('/events')
export const addFuelEvent = (event) => post('/events', event)
export const importFuelCsv = (text, sourceId = 'manual_csv') => post('/import/csv', { text, source_id: sourceId })
export const importIataCsv = (text) => post('/import/iata', { text })
export const importBtsCsv = (text) => post('/import/bts', { text })
export const fetchFuelAdjustments = () => request('/adjustments')
export const saveFuelAdjustment = (adjustment) => post('/adjustments', adjustment)
