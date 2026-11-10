// Market Opportunities: the cross-country wholesale price comparison and its opportunity rating. The ENGINE runs on the server now (backend/market_opportunities/, routers/
// market_opportunities.py): product collection, translation, name / curated / AI / shared-HS-code matching, currency and unit conversion, item-weight research, the comparison
// rows and the saving. This file only starts it, follows it and reads the saved results. A parity test (backend/tests/test_market_opportunities_parity.py) holds the Python to
// exactly what the old 740-line JavaScript engine produced on the same data.
import { API_BASE } from './apiBase'

const POLL_MS = 2000
const MAX_WAIT_MS = 30 * 60 * 1000 // the AI judge and the web research can take minutes

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const postJson = (path, body) => fetchJson(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// { rate, date, from, available } — how many units of `fromCurrency` equal 1 USD (DIVIDE a local price by it); `available: false` when the currency has no rate anywhere.
export async function fetchMarketOpportunityExchangeRate(fromCurrency) {
  const params = new URLSearchParams({ from: fromCurrency })
  return fetchJson(`/api/market-opportunities/exchange-rate?${params.toString()}`)
}

// A comparison of one source country against target countries: the saved one when every target already has one (no recompute, no AI calls), otherwise — or with `force` — a
// fresh run on the server, saved before it is returned. `onStatus('checking' | 'computing')` reports which is happening.
// -> { rows (with _target_display_name), unmatchedByTarget, unmatchedUnknown, calculatedAt, origin: 'saved' | 'computed', aiMatchErrors, weightError }
export async function getOrComputeComparison(sourceCountry, targetCountries, { force = false, onStatus } = {}) {
  const withDisplayName = (rows) => rows.map((row) => ({ ...row, _target_display_name: row.target_product_name }))
  if (!force) {
    onStatus?.('checking')
    const saved = await fetchMarketOpportunityComparisons(sourceCountry, targetCountries).catch(() => null)
    const savedTargets = new Set((saved?.rows || []).map((row) => row.target_country))
    if (saved && targetCountries.every((name) => savedTargets.has(name))) {
      const unmatched = saved.unmatched_by_target || {}
      return {
        rows: withDisplayName(saved.rows),
        unmatchedByTarget: unmatched,
        // a saved run from before the unmatched list was stored
        unmatchedUnknown: targetCountries.some((name) => !(name in unmatched)),
        // the oldest of the targets' runs — the whole result is at least that old
        calculatedAt: saved.rows.map((row) => row.calculated_at).sort()[0] ?? null,
        origin: 'saved',
        aiMatchErrors: {},
      }
    }
  }
  onStatus?.('computing')
  const body = { source_country: sourceCountry, target_countries: targetCountries, force: true, allow_ai: true, allow_research: true, save: true }
  let state = await postJson('/api/market-opportunities/compute', body)
  const begun = Date.now()
  while (state.status === 'building') {
    if (Date.now() - begun > MAX_WAIT_MS) throw new Error('The comparison is taking longer than expected; it keeps running on the server — open it again in a few minutes.')
    // eslint-disable-next-line no-await-in-loop -- polls until the job is done
    await new Promise((resolve) => setTimeout(resolve, POLL_MS))
    // eslint-disable-next-line no-await-in-loop
    state = await fetchJson(`/api/market-opportunities/compute/status?${new URLSearchParams({ source_country: sourceCountry, target_countries: targetCountries.join(',') })}`)
  }
  if (state.status === 'error') throw new Error(state.error || 'The comparison failed.')
  const result = state.result
  const shared = { unmatchedByTarget: result.unmatched_by_target, unmatchedUnknown: false, origin: 'computed', aiMatchErrors: result.ai_errors || {}, weightError: result.weight_error || null }
  if (!result.row_count) return { ...shared, rows: [], calculatedAt: new Date().toISOString() }
  const saved = await fetchMarketOpportunityComparisons(sourceCountry, targetCountries)
  return { ...shared, rows: withDisplayName(saved.rows), calculatedAt: result.calculated_at }
}

// Priority list of one source country's comparisons: items are { source_country, target_country, product_name }.
export async function fetchMarketOpportunityPriority(sourceCountry, targetCountries) {
  const params = new URLSearchParams({ source_country: sourceCountry, target_countries: targetCountries.join(',') })
  return fetchJson(`/api/market-opportunities/priority?${params.toString()}`)
}

export const addToMarketOpportunityPriority = (items) => postJson('/api/market-opportunities/priority', { items })
export const removeFromMarketOpportunityPriority = (items) => postJson('/api/market-opportunities/priority/remove', { items })

// Every saved source -> target comparison: [{ source_country, target_country, row_count, calculated_at, stale, stale_reasons }] — `stale` says whether the catalogs, HS codes,
// item weights or translations changed after it was calculated, `stale_reasons` says what in words.
export async function fetchMarketOpportunityPairs() {
  return fetchJson('/api/market-opportunities/comparisons/pairs')
}

export async function fetchMarketOpportunityComparisons(sourceCountry, targetCountries) {
  const params = new URLSearchParams({ source_country: sourceCountry, target_countries: targetCountries.join(',') })
  return fetchJson(`/api/market-opportunities/comparisons?${params.toString()}`)
}

/** Every product of a country's portfolio with its price per kg in USD (null where the unit or currency couldn't be converted) and its HS code:
 * [{ name, category, hsCode, priceUsdPerKg, original: { value, unit, currency } | null, source }]. Matched in another market or not — the same prices the comparison uses. */
export async function fetchCountryProductPrices(countryName) {
  const { products } = await fetchJson(`/api/market-opportunities/country-prices?${new URLSearchParams({ country: countryName })}`)
  return products
}
