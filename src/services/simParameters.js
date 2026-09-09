import { API_BASE } from './apiBase'

export async function fetchSimParameters(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/sim-parameters`)
  if (!response.ok) throw new Error('Failed to load sim parameters')
  return response.json()
}

export async function createSimParameter(companyId, entryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/sim-parameters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entry_id: entryId }),
  })
  if (!response.ok) throw new Error('Failed to flag sim parameter')
  return response.json()
}

export async function deleteSimParameter(companyId, entryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/sim-parameters/${entryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to remove sim parameter')
  return response.json()
}
