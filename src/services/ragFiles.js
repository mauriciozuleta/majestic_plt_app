import { API_BASE } from './apiBase'

// RAG Files: per-country documents that are converted to JSON ("Load") and
// baked into the country's RAG file ("Bake") — backend/routers/rag_files.py.

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const country = (name) => `/rag-files/countries/${encodeURIComponent(name)}`

// -> { countries: [{ country, country_code, files, uploaded, loaded, baked, error,
//      needs_bake, baked_at, chunk_count, embedded, job }], supported_extensions }
export const fetchRagCountries = () => request('/rag-files/countries')

// -> the same counts + file_list: [{ name, format, size_bytes, status, error,
//    sections, characters, loaded_at, warnings }] and job: { kind, status, message, done, total }
export const fetchRagCountry = (name) => request(country(name))

const toBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`))
    reader.readAsDataURL(file)
  })

export const addRagFile = async (name, file) =>
  request(`${country(name)}/files`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, content_base64: await toBase64(file) }),
  })

export const deleteRagFile = (name, filename) => request(`${country(name)}/files/${encodeURIComponent(filename)}`, { method: 'DELETE' })

// The converted JSON of a loaded file: { title, source, stats, warnings, sections: [{ id, title, path, level, content }] }
export const fetchRagDocument = (name, filename) => request(`${country(name)}/files/${encodeURIComponent(filename)}/json`)

export const loadRagFiles = (name) => request(`${country(name)}/load`, { method: 'POST' })
export const bakeRagFiles = (name) => request(`${country(name)}/bake`, { method: 'POST' })

export const searchRagFiles = (name, query) =>
  request(`${country(name)}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })

// The shared Load/Bake queue (one job runs at a time) ->
// { active: [{ id, country, kind, status: 'running'|'queued', message, done, total, position }], recent: [...] }
export const fetchRagQueue = () => request('/rag-files/queue')
export const cancelRagJob = (id) => request(`/rag-files/queue/${id}/cancel`, { method: 'POST' })
// queues a Bake for every country with loaded documents that are not baked yet
export const bakeAllPending = () => request('/rag-files/queue/bake-pending', { method: 'POST' })
