// Cached Haiku (no web search, no tools) unit-pack-weight estimates, for
// Market Opportunities' count-vs-weight conversion (see
// MarketAnalysis/countWeightConversion.js). Deliberately NOT
// weightResearch.js above — that's a different, more expensive (Sonnet +
// web search), background-job-backed mechanism for a different purpose.
// This endpoint is synchronous (a no-tools Haiku call is fast), so there's
// no polling loop here — just a request/response, same as any other fetch
// in this app.

import { API_BASE } from './apiBase'

export async function fetchUnitWeightEstimates() {
  const response = await fetch(`${API_BASE}/api/unit-weight-estimates`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

// `dryRun: true` checks the cache and reports hit/miss counts WITHOUT
// calling Haiku or writing anything — used to report the real pre-spend
// cost (how many distinct products would need a fresh call) before
// actually requesting estimates for a batch.
export async function requestUnitWeightEstimates(items, { dryRun = false } = {}) {
  if (items.length === 0) return { results: {}, cache_hit_count: 0, cache_miss_count: 0 }
  const response = await fetch(`${API_BASE}/api/unit-weight-estimates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, dry_run: dryRun }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
