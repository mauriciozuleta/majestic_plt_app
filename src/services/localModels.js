import { API_BASE } from './apiBase'

// Local models (Ollama) — used only to build reports from a country's baked
// RAG files (backend/routers/local_models.py).

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// -> { available, base_url, detail, models: [{ name, size_bytes, parameter_size, family, vision, thinking }] }
export const fetchLocalModels = (refresh = false) => request(`/local-models${refresh ? '?refresh=true' : ''}`)

// { model, country, request } -> job { id, status: running | done | failed | cancelled,
// status_text, text (so far), sources: [{ number, document, section }], error }
export const startLocalReport = (payload) => request('/local-models/report', json('POST', payload))
export const fetchLocalReport = (jobId) => request(`/local-models/report/${jobId}`)
// Saves a built report as Markdown in the country's `reports` folder -> { file, folder }
export const saveLocalReport = (payload) => request('/local-models/reports/save', json('POST', payload))
export const cancelLocalReport = (jobId) => request(`/local-models/report/${jobId}/cancel`, { method: 'POST' })

// Tax-cost PDF for the products of one opportunity category: { model, country, rating } ->
// job { id, status, status_text, done, total, eta_seconds, rows, summary, file, folder, error }.
// The PDF itself is GET /local-models/tax-report/{id}/pdf.
export const startTaxReport = (payload) => request('/local-models/tax-report', json('POST', payload))
export const fetchTaxReport = (jobId) => request(`/local-models/tax-report/${jobId}`)
export const cancelTaxReport = (jobId) => request(`/local-models/tax-report/${jobId}/cancel`, { method: 'POST' })

// Download link of a saved report (PDF/Markdown) in a country's `reports` folder.
export const reportFileUrl = (country, file) => `${API_BASE}/local-models/reports/file?country=${encodeURIComponent(country)}&file=${encodeURIComponent(file)}`
