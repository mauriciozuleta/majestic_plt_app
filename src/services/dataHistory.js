import { API_BASE } from './apiBase'

// Data history (backend/routers/data_history.py): the versions of every stored dataset, restore, and the approval of refreshes that looked worse
// than what is stored.

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })
const query = (params) => new URLSearchParams(Object.entries(params).filter(([, value]) => value != null)).toString()

export const fetchDataHistoryDatasets = () => request('/api/data-history/datasets')
export const fetchDataHistoryLog = (scope) => request(`/api/data-history/log?${query({ scope })}`)
export const fetchDataHistoryDiff = (scope, to, from) => request(`/api/data-history/diff?${query({ scope, to, from })}`)
export const restoreDataVersion = (scope, version) => request('/api/data-history/restore', post({ scope, version }))
export const pinDataVersion = (scope, version, pinned) => request('/api/data-history/pin', post({ scope, version, pinned }))
export const fetchHeldUpdates = () => request('/api/data-history/held')
export const approveHeldUpdate = (id) => request(`/api/data-history/held/${id}/approve`, post())
export const rejectHeldUpdate = (id) => request(`/api/data-history/held/${id}/reject`, post())
