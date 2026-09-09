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
