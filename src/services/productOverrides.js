// User-entered price/weight corrections for one exact priced row — the
// manual escape hatch for when the official conversion is missing and AI
// research (see weightResearch.js) is wrong, stale, or hasn't run yet.
// Plain synchronous CRUD (no background job — this never calls an
// external API). Global, not per-company, matching weight research.

import { API_BASE } from './apiBase'

export async function fetchCustomOverrides() {
  const response = await fetch(`${API_BASE}/product-custom-overrides`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

// The signature travels in the request body, not the URL path — these
// signatures routinely contain "/" (e.g. a USA unit like "USD/lb"), which
// even percent-encoded doesn't reliably survive as a single path segment.
export async function saveCustomOverride(signature, { customPrice, customWeightKg }) {
  const response = await fetch(`${API_BASE}/product-custom-overrides`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ signature, custom_price: customPrice, custom_weight_kg: customWeightKg }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function clearCustomOverride(signature) {
  const response = await fetch(`${API_BASE}/product-custom-overrides/clear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ signature }),
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}
