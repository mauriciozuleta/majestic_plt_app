import { API_BASE } from './apiBase'

export async function fetchReferenceRegions() {
  const response = await fetch(`${API_BASE}/reference-regions`)
  if (!response.ok) throw new Error('Failed to load reference regions')
  return response.json()
}

export async function fetchReferenceCountries(region) {
  const query = region ? `?region=${encodeURIComponent(region)}` : ''
  const response = await fetch(`${API_BASE}/reference-countries${query}`)
  if (!response.ok) throw new Error('Failed to load reference countries')
  return response.json()
}

export async function fetchCommercialRegions(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-regions`)
  if (!response.ok) throw new Error('Failed to load regions')
  return response.json()
}

export async function fetchCommercialCountries(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries`)
  if (!response.ok) throw new Error('Failed to load countries')
  return response.json()
}

export async function fetchCommercialBranches(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-branches`)
  if (!response.ok) throw new Error('Failed to load branches')
  return response.json()
}

export async function createCommercialRegion(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-regions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to create region')
  return response.json()
}

export async function createCommercialCountry(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to create country')
  return response.json()
}

export async function createCommercialBranch(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-branches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to create branch')
  return response.json()
}
