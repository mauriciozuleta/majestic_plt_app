// Market Opportunities' AI match tier (backend/routers/product_matches.py):
// cached Claude Haiku judgement of which target-market products are the same
// product as each still-unmatched source product.
import { API_BASE } from './apiBase'

// groups: [{ candidates: [targetName], sources: [{ key, description }] }].
// Resolves to { results: { [key]: { matches, note, cached } } }.
export async function requestProductMatches(targetCountry, groups) {
  const response = await fetch(`${API_BASE}/api/product-matches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_country: targetCountry, groups }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
