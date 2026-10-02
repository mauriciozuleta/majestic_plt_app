import { API_BASE } from './apiBase'

export async function fetchRevenueStreams(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams`)
  if (!response.ok) throw new Error('Failed to load revenue streams')
  return response.json()
}

export async function createRevenueStream(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to create revenue stream')
  }
  return response.json()
}

// Origin -> destination routes (pairs of commercial-structure branches) on a
// company's revenue streams.
export async function fetchRevenueStreamRoutes(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams/routes`)
  if (!response.ok) throw new Error('Failed to load revenue stream routes')
  return response.json()
}

export async function createRevenueStreamRoute(companyId, streamId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams/${streamId}/routes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to save the route')
  }
  return response.json()
}

export async function updateRevenueStreamRoute(companyId, streamId, routeId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams/${streamId}/routes/${routeId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to update the route')
  }
  return response.json()
}

export async function deleteRevenueStreamRoute(companyId, streamId, routeId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/revenue-streams/${streamId}/routes/${routeId}`, { method: 'DELETE' })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to delete the route')
  }
}
