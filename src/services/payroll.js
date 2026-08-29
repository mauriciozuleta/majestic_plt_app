import { API_BASE } from './apiBase'

export async function fetchPayroll(companyId, year = 0) {
  const safeYear = Number.isFinite(Number(year)) ? Number(year) : 0
  const params = new URLSearchParams({ year: String(safeYear) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll?${params.toString()}`)
  if (!response.ok) throw new Error('Failed to load payroll')
  return response.json()
}

export async function createPosition(companyId, position, year = 0) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/payroll-positions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...position, projection_year: Number(year) }),
  })
  if (!response.ok) throw new Error('Failed to create position')
  return response.json()
}

export async function updatePosition(nodeId, updates, year = 0) {
  const response = await fetch(`${API_BASE}/payroll-positions/${nodeId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...updates, projection_year: Number(year) }),
  })
  if (!response.ok) throw new Error('Failed to update position')
  return response.json()
}

export async function clonePosition(nodeId) {
  const response = await fetch(`${API_BASE}/payroll-positions/${nodeId}/clone`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to clone position')
  return response.json()
}