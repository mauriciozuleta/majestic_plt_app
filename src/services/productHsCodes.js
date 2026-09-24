// Real UN Comtrade HS codes for our own wholesale products (see
// backend/comtrade/product_classification.py) — what the General Portfolio
// Directory's product code is built from, e.g. onions from Colombia get
// "CO070310" instead of an arbitrary sequence number.
//
// Classifying a batch of new names can take minutes (several sequential
// Claude calls) — same "runs as a background task, GET is always instant"
// shape as weightResearch.js, except this one is fire-and-forget rather
// than polled: it's invisible background enrichment, not something a user
// explicitly asks for and waits on. A product not yet classified just shows
// its old fallback code on this view and picks up the real one on the next.

import { API_BASE } from './apiBase'

// { building, error, results: { [key]: { hs_code, description } | null } } — every product classified so far.
export async function fetchProductHsCodes() {
  const response = await fetch(`${API_BASE}/api/product-hs-codes`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

// items: [{ key, name }]. Starts classifying whatever isn't already cached,
// in the background, and returns immediately — never awaited by callers
// that just want today's best-available codes.
export async function startProductClassification(items) {
  if (items.length === 0) return { status: 'no_items' }
  const response = await fetch(`${API_BASE}/api/product-hs-codes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(items),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
