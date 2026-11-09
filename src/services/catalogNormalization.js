// The catalog normalization module's API (backend/routers/catalog_normalization.py): research of the weight of one item of a product on the web, and the
// conversion of one catalog row with what has been researched. It replaces the old Haiku "unit weight estimate" and "weight research" calls.
import { API_BASE } from './apiBase'

const BASE = `${API_BASE}/api/catalog-normalization`
const POLL_MS = 4000
const MAX_WAIT_MS = 20 * 60 * 1000 // a batch of web research takes a few minutes

async function request(path, options) {
  const response = await fetch(`${BASE}${path}`, options)
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`)
  return body
}

export const fetchNormalizationStatus = () => request('/status')

// Researches the weight of one item for these products (the names the module reads: the English name for Colombia) and waits for the job to finish.
// -> { started, pending, error } — `error` is the reason the job failed (an Anthropic API problem, for instance), null when it worked.
export async function researchProductWeights(names, { limit = 48 } = {}) {
  const started = await request('/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ names, limit }),
  })
  if (started.status === 'nothing_to_do') return { started: false, pending: 0, error: null }
  const begun = Date.now()
  // eslint-disable-next-line no-constant-condition -- polls until the job is done or the wait runs out
  while (true) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, POLL_MS))
    // eslint-disable-next-line no-await-in-loop
    const status = await fetchNormalizationStatus()
    if (!status.researching) return { started: true, pending: status.pending_research, error: status.error || null }
    if (Date.now() - begun > MAX_WAIT_MS) return { started: true, pending: status.pending_research, error: 'The weight research is taking longer than expected; it keeps running in the background.' }
  }
}

// One catalog row converted with what is in the store now: { price_per_kg, method, confidence, note, ... }
export function convertCatalogRow(name, unit, price) {
  const query = new URLSearchParams({ name, unit: unit ?? '', ...(price != null ? { price: String(price) } : {}) })
  return request(`/convert?${query.toString()}`)
}

// ---- the form behind the red "need data" pill of Market Analysis ▸ Country Product Portfolio

// { [country name]: how many products still have no item weight }
export const fetchMissingSummary = () => request('/missing-summary').then((data) => data.countries)

// the products of one country with the rows that need a weight: [{ name, count_unit, rows, sources, examples: [{ label, unit_text, price, source }] }]
export const fetchMissingItems = (country) => request(`/missing?country=${encodeURIComponent(country)}`).then((data) => data.items)

const post = (path, body) => request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// items: [{ name, count_unit, weight_g, min_g?, max_g? }] -> [{ status: 'ok' | 'warning' | 'error', messages, previews }]
export const validateWeights = (items) => post('/validate', { items }).then((data) => data.results)

// The AI search: researches the weight of one item on the web for these products (at most 12) and returns it, validated, WITHOUT saving.
// -> [{ name, count_unit, weight_g, min_g, max_g, confidence, note, sources, validation }]
export const suggestWeights = (items) => post('/suggest', { items: items.map(({ name, count_unit }) => ({ name, count_unit })) }).then((data) => data.results)

// items: [{ name, count_unit, weight_g, min_g?, max_g?, origin: 'manual' | 'ai', confidence?, note?, sources? }] -> { saved, refused, still_missing }
export const saveWeights = (items) => post('/weights', { items })
