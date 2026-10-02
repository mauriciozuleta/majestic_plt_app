// COS/Expenses ▸ Providers ▸ Air Logistics (backend/routers/air_logistics.py):
// a company's aircraft catalog and the charter providers that fly them.
import { API_BASE } from './apiBase'

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.status === 204 ? null : response.json()
}

const json = (method, payload) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })

export const fetchAircraft = (companyId) => request(`/companies/${companyId}/air-logistics/aircraft`)
export const fetchAircraftCatalogue = (companyId) => request(`/companies/${companyId}/air-logistics/aircraft-catalogue`)
export const addAircraftToFleet = (companyId, aircraftIds) =>
  request(`/companies/${companyId}/air-logistics/fleet`, json('POST', { aircraft_ids: aircraftIds }))
export const removeAircraftFromFleet = (companyId, aircraftId) =>
  request(`/companies/${companyId}/air-logistics/fleet/${aircraftId}`, { method: 'DELETE' })
export const saveAircraft = (companyId, aircraftId, payload) =>
  aircraftId
    ? request(`/companies/${companyId}/air-logistics/aircraft/${aircraftId}`, json('PUT', payload))
    : request(`/companies/${companyId}/air-logistics/aircraft`, json('POST', payload))
export const deleteAircraft = (companyId, aircraftId) =>
  request(`/companies/${companyId}/air-logistics/aircraft/${aircraftId}`, { method: 'DELETE' })

export const fetchCharterProviders = (companyId) => request(`/companies/${companyId}/air-logistics/charter-providers`)
export const saveCharterProvider = (companyId, providerId, payload) =>
  providerId
    ? request(`/companies/${companyId}/air-logistics/charter-providers/${providerId}`, json('PUT', payload))
    : request(`/companies/${companyId}/air-logistics/charter-providers`, json('POST', payload))
export const deleteCharterProvider = (companyId, providerId) =>
  request(`/companies/${companyId}/air-logistics/charter-providers/${providerId}`, { method: 'DELETE' })
