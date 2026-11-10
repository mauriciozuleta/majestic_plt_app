// Shipments: what the route table and the shipment cards show, the Shipment builder's candidates and the sharing of the kilos are computed on the SERVER now
// (backend/shipments/, routers/shipments.py). This file only asks for them. A parity test (backend/tests/test_shipments_parity.py) holds the Python to exactly the
// numbers and words the old JavaScript produced.
import { API_BASE } from './apiBase'

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

// A route's page asks for the same figures several times at once (the route row, each leg's cards, the shipment panel): one request serves them, for a few seconds.
// `version` summarises what the figures depend on, so an edited route is asked for again.
const CACHE_MS = 5000
const cache = new Map()

/** For one revenue route and each of its legs (`outbound`, `return`): { airfare_per_kg, airfare_note, metrics, figures: { revenue, cos, profit, notes, ... } | null,
 * countries: { source, target } | null, comparison: { calculated_at, stale, stale_reasons } | null, error,
 * shipment: { ...built shipment, items: [{ ...item, cost, level, sale }], ddpTotal, saleTotal } | null } — `comparison.stale` says the saved Market Opportunities
 * comparison the shipment is priced from is out of date. */
export function fetchRouteFinance(routeId, version = '') {
  const key = `${routeId}|${version}`
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.promise
  const promise = fetchJson(`/api/shipments/route-finance?${new URLSearchParams({ route_id: routeId })}`)
  cache.set(key, { at: Date.now(), promise })
  promise.catch(() => cache.delete(key))
  return promise
}

/** The products a shipment of source -> target can be built from: { status: 'no_priority' | 'no_comparison' | 'ready', groups: [{ rating, products }], missingPriority,
 * comparison, samError, countries }. Each product has its rating, Country SAM, market level, cargo cap and margin. */
export const fetchShipmentCandidates = (sourceCountry, targetCountry, airfarePerKg) => {
  const params = new URLSearchParams({ source_country: sourceCountry, target_country: targetCountry })
  if (airfarePerKg != null) params.set('airfare_per_kg', String(airfarePerKg))
  return fetchJson(`/api/shipments/candidates?${params}`)
}

/** Shares the aircraft's capacity over the picked candidates -> { items: [{ ...product, kg, sharePct, manual }], allocatedKg, unallocatedKg }. `fixedKg`: { productKey: kg typed by hand }. */
export const allocateShipment = (products, capacityKg, fixedKg = {}) =>
  fetchJson('/api/shipments/allocate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ products, capacity_kg: capacityKg, fixed_kg: fixedKg }) })

// Has a shipment been built for source -> targets, and what is that route's air fare per kg? -> Map(target -> { airfarePerKg, note, routeName }), only for targets with a built shipment
export async function fetchBuiltShipmentAirfares(sourceCountry, targetCountries) {
  const { airfares } = await fetchJson(`/api/shipments/airfares?${new URLSearchParams({ source_country: sourceCountry, target_countries: targetCountries.join(',') })}`)
  return new Map(Object.entries(airfares))
}
