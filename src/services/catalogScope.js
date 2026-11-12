// The catalog scope: which downloaded products are in the main catalog and which were set aside in the secondary (discarded) list. Decided on the SERVER
// (backend/catalog_normalization/scope.py, routers/catalog_scope.py); this file only asks for the list and sends the person's moves.
import { API_BASE } from './apiBase'

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

/** -> { total: { main, secondary, check, moved_by_you }, reasons: { reason: count }, sources: [{ source, name, country, main, secondary, check, moved_by_you }] } */
export const fetchScopeSummary = () => request('/api/catalog-scope/summary')

/** The secondary (discarded) list, or with status 'main' the main catalog. The ones the rules were unsure about come first.
 * -> { total, items: [{ source, source_name, country, name, category, price, unit, currency, hs6, status, reason, rule, confidence, per_kg }] } */
export function fetchScopeItems({ status = 'secondary', country, source, query, reason, limit = 300, offset = 0 } = {}) {
  const params = new URLSearchParams({ status, limit: String(limit), offset: String(offset) })
  if (country) params.set('country', country)
  if (source) params.set('source', source)
  if (query) params.set('q', query)
  if (reason) params.set('reason', reason)
  return request(`/api/catalog-scope/items?${params}`)
}

/** Moves products ({ source, name }) to 'main' (return them to the catalog) or 'secondary' (set them aside). The choice is kept when the catalog is downloaded again. */
export const moveScopeItems = (items, to) =>
  request('/api/catalog-scope/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items, to }) })
