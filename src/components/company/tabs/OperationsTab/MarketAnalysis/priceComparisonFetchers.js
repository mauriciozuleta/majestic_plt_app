// Live source fetchers — call the backend, which resolves La Mayorista's
// current Google Sheets ID from their homepage and downloads/parses it,
// and downloads/parses today's Corabastos bulletin PDF. Each request is
// independent: one source failing (site down, no bulletin published today,
// unexpected page structure) never blocks the other's data from loading.
// No polling/scheduling here — this only ever runs from the Update button.

import { API_BASE } from '../../../../../services/apiBase'
import { useAppStore } from '../../../../../store/useAppStore'

const SUGGESTION_POLL_INTERVAL_MS = 5000

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

export async function fetchTranslationSuggestions() {
  return fetchJson('/market-analysis/colombia/translation-suggestions')
}

export async function startTranslationSuggestions(items) {
  return fetchJson('/market-analysis/colombia/translation-suggestions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
}

// Kicks off (or joins, if one is already running) the background Tier 3/4
// translation-suggestion job and resolves once it's done — same "survives
// navigating away, polled since 'done' is `building` going false" shape as
// researchMissingWeights (services/weightResearch.js).
export function requestTranslationSuggestions(items) {
  return startTranslationSuggestions(items).then((startResult) => {
    if (startResult.status === 'no_items' || startResult.status === 'already_building') return fetchTranslationSuggestions()
    return new Promise((resolve, reject) => {
      const tick = () => {
        fetchTranslationSuggestions()
          .then((data) => {
            if (data.building) {
              setTimeout(tick, SUGGESTION_POLL_INTERVAL_MS)
              return
            }
            if (data.error) {
              useAppStore.getState().addAssistantMessage(`Translation suggestions failed: ${data.error}`)
              reject(new Error(data.error))
              return
            }
            useAppStore.getState().addAssistantMessage('AI translation suggestions are ready — review them before confirming.')
            resolve(data)
          })
          .catch(reject)
      }
      tick()
    })
  })
}

export async function confirmTranslationSuggestion(productKey) {
  return fetchJson(`/market-analysis/colombia/translation-suggestions/${encodeURIComponent(productKey)}/confirm`, {
    method: 'POST',
  })
}

export async function rejectTranslationSuggestion(productKey) {
  return fetchJson(`/market-analysis/colombia/translation-suggestions/${encodeURIComponent(productKey)}`, {
    method: 'DELETE',
  })
}
