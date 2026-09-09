// Live source fetchers — call the backend, which resolves La Mayorista's
// current Google Sheets ID from their homepage and downloads/parses it,
// and downloads/parses today's Corabastos bulletin PDF. Each request is
// independent: one source failing (site down, no bulletin published today,
// unexpected page structure) never blocks the other's data from loading.
// No polling/scheduling here — this only ever runs from the Update button.

import { API_BASE } from '../../../../../services/apiBase'

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function fetchLaMayoristaPrices() {
  return fetchJson('/market-analysis/colombia/la-mayorista')
}

export async function fetchCorabastosPrices() {
  return fetchJson('/market-analysis/colombia/corabastos')
}

export async function fetchPriceComparisonSnapshot() {
  return fetchJson('/market-analysis/colombia/snapshot')
}

export async function fetchTranslationOverrides() {
  return fetchJson('/market-analysis/colombia/translations')
}

export async function saveTranslationOverride(productKey, translationEn) {
  return fetchJson('/market-analysis/colombia/translations', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_key: productKey, translation_en: translationEn }),
  })
}
