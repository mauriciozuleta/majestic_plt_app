import { API_BASE } from './apiBase'

export async function fetchCommercialOperationEntries(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-operations`)
  if (!response.ok) throw new Error('Failed to load commercial operations entries')
  return response.json()
}

export async function createCommercialOperationEntry(companyId, entry) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-operations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  })
  if (!response.ok) throw new Error('Failed to add entry')
  return response.json()
}

export async function deleteCommercialOperationEntry(companyId, entryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/commercial-operations/${entryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to delete entry')
  return response.json()
}
