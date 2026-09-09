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

export async function updateCommercialRegion(companyId, regionId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-regions/${regionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to update region')
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

export async function updateCommercialCountry(companyId, countryId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/${countryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to update country')
  return response.json()
}

export async function fetchProfiledCountries(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/profiles`)
  if (!response.ok) throw new Error('Failed to load countries with a commercial profile')
  return response.json()
}

export async function fetchAllCompetitivenessAnalyses(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/competitiveness-analyses`)
  if (!response.ok) throw new Error('Failed to load competitiveness analyses')
  return response.json()
}

export async function fetchCompetitivenessAnalysis(companyId, targetCountryId, sourceCountryName) {
  const response = await fetch(
    `${API_BASE}/companies/${companyId}/commercial-countries/${targetCountryId}/competitiveness?source_country_name=${encodeURIComponent(sourceCountryName)}`,
  )
  if (!response.ok) throw new Error('Failed to load the competitiveness analysis')
  return response.json()
}

export async function buildCompetitivenessAnalysis(companyId, targetCountryId, sourceCountryName, categorySummary) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/${targetCountryId}/competitiveness`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_country_name: sourceCountryName, category_summary: categorySummary }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to build the competitiveness analysis')
  }
  return response.json()
}

export async function fetchCountryProfile(companyId, countryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/${countryId}/profile`)
  if (!response.ok) throw new Error('Failed to load country profile')
  return response.json()
}

export async function buildCountryProfile(companyId, countryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/${countryId}/profile`, { method: 'POST' })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to build country profile')
  }
  return response.json()
}

export async function deleteCommercialCountry(companyId, countryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-countries/${countryId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete country')
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

export async function updateCommercialBranch(companyId, branchId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-branches/${branchId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('Failed to update branch')
  return response.json()
}

export async function deleteCommercialBranch(companyId, branchId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-branches/${branchId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete branch')
}
