import { API_BASE } from './apiBase'

// Deletes products from the product catalog (the Country Product Portfolio). `items` are { source, id?, category, name, unit, detail?, pack? } with
// source = the snapshot key (la_mayorista, corabastos, usa_*, custom_<id>); the backend also writes a modification report into Documentation.
export async function deleteCatalogProducts(items, deletedBy) {
  const response = await fetch(`${API_BASE}/catalog-products/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, deleted_by: deletedBy || '' }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `Could not delete the products (${response.status})`)
  }
  return response.json()
}
