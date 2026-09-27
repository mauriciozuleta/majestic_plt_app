// Variety Gallery API (backend/routers/species_gallery.py) — scientific-name
// anchoring, the persistent Species/Variety database, cache-first bootstrap,
// cross-market matching, and the review queue. See
// backend/species_gallery/__init__.py for the subsystem's own overview and
// SPECIES_GALLERY_METHODOLOGY.md for the full design.
//
// Every call here goes through the public /api/species-gallery/* surface —
// the one exception is fetchVarietyAdmin, used only by an internal/admin
// view, which is the only response shape carrying image_tier_a at all (see
// backend/schemas.py's VarietyPublicOut vs VarietyAdminOut).

import { API_BASE } from './apiBase'

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function fetchConfigStatus() {
  return request('/api/species-gallery/config-status')
}

export async function resolveSpecies(items) {
  return request('/api/species-gallery/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
}

export async function fetchSpeciesList() {
  return request('/api/species-gallery/species')
}

export async function fetchVarietiesPublic(scientificName) {
  return request(`/api/species-gallery/species/${encodeURIComponent(scientificName)}/varieties`)
}

export async function bootstrapVariety({ scientificName, commonName, varietyName, sourceCountry, category = 'produce' }) {
  return request('/api/species-gallery/varieties/bootstrap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scientific_name: scientificName,
      common_name: commonName,
      variety_name: varietyName,
      source_country: sourceCountry,
      category,
    }),
  })
}

export async function fetchReviewQueue() {
  return request('/api/species-gallery/review-queue')
}

export async function confirmVariety(varietyId) {
  return request(`/api/species-gallery/review-queue/${encodeURIComponent(varietyId)}/confirm`, { method: 'POST' })
}

export async function rejectVariety(varietyId) {
  return request(`/api/species-gallery/review-queue/${encodeURIComponent(varietyId)}`, { method: 'DELETE' })
}

export async function matchVariety({ sourceVarietyId, targetCountry, category = 'produce' }) {
  return request('/api/species-gallery/match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_variety_id: sourceVarietyId, target_country: targetCountry, category }),
  })
}

// Reports how many (species, variety, country) combinations WOULD need a
// real bootstrap (LangSearch/Commons calls) without making any — the
// pre-bulk-run cost guardrail this feature's own spec requires. `items` is
// [{name, hs_description, countries: [countryName, ...]}].
export async function requestCostGuardrail(items) {
  return request('/api/species-gallery/cost-guardrail', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
}
