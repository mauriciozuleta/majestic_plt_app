import { API_BASE } from './apiBase'

// HS codes of the catalog products (backend/routers/hs_codes.py, backend/catalog_normalization/hs.py). A suggestion is never saved by itself: `saveHsCodes` is
// what a person's "Save to DB" calls.

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// { total: {no_code, heading_only, suggested, confirmed}, countries: { [country]: {...} } }
export const fetchHsStatus = () => request('/api/hs-codes/status')

// the products to look at next: no code, heading only, with a warning, unreviewed — products in a saved comparison first
export const fetchHsQueue = (country, { limit = 300, includeConfirmed = false } = {}) =>
  request(`/api/hs-codes/queue?${new URLSearchParams({ country, limit, include_confirmed: includeConfirmed })}`)

// items: [{ country, name, category, code }] -> { results: [{ status, messages, hs6, level, description }] }
export const validateHsCodes = (items) => request('/api/hs-codes/validate', post(items)).then((data) => data.results)

// free sources (a curated rule, the same product in another country, keyword rules, the Schedule B text) always; Claude (credits) only when asked
export const suggestHsCodes = (items, { allowAi = false } = {}) =>
  request('/api/hs-codes/suggest', post({ items, allow_peer: true, allow_ai: allowAi }))

// items: [{ country, name, category, code, method, confidence, note }] -> { saved, refused: [{ name, messages }] }
export const saveHsCodes = (items, savedBy = 'user') => request('/api/hs-codes/save', post({ items, saved_by: savedBy }))
