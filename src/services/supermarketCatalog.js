import { API_BASE } from './apiBase'

// Supermarket catalogs, built by the separate Supermarket_data_fetch app
// through its local API (see backend/routers/supermarket_catalog.py).

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// -> { available, detail, api_url, stores: [{ id, name, country }] }
export const fetchSupermarketCatalogStatus = () => request('/supermarket-catalog/status')

// Both return a job: { id, kind, status: running | done | failed | cancelled |
// interaction_required, messages: [{ at, text }], progress, result, error }
export const prepareSupermarketCatalog = (payload) => request('/supermarket-catalog/prepare', json('POST', payload))
// { store_id, category: { name, url }, categories } -> job whose result is
// { children, categories } — `categories` merged with the subcategories found.
export const findSupermarketSubcategories = (payload) => request('/supermarket-catalog/subcategories', json('POST', payload))
export const downloadSupermarketCatalog = (payload) => request('/supermarket-catalog/download', json('POST', payload))

// A finished download job also carries `import`: { status: 'imported', source,
// product_count, file } once its file is loaded into the product sources.
export const fetchSupermarketCatalogJob = (jobId) => request(`/supermarket-catalog/jobs/${jobId}`)
export const cancelSupermarketCatalogJob = (jobId) => request(`/supermarket-catalog/jobs/${jobId}/cancel`, { method: 'POST' })
