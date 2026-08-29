import { API_BASE } from './apiBase'

export async function fetchOrgChartNodes(companyId, year = 0) {
  const safeYear = Number.isFinite(Number(year)) ? Number(year) : 0
  const params = new URLSearchParams({ year: String(safeYear) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/org-chart-nodes?${params.toString()}`)
  if (!response.ok) throw new Error('Failed to load org chart nodes')
  return response.json()
}

export async function fetchOrgChartEdges(companyId, year = 0) {
  const safeYear = Number.isFinite(Number(year)) ? Number(year) : 0
  const params = new URLSearchParams({ year: String(safeYear) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/org-chart-edges?${params.toString()}`)
  if (!response.ok) throw new Error('Failed to load org chart edges')
  return response.json()
}

export async function createOrgChartNode(companyId, node, year = 0) {
  const safeYear = Number.isFinite(Number(year)) ? Number(year) : 0
  const params = new URLSearchParams({ year: String(safeYear) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/org-chart-nodes?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(node),
  })
  if (!response.ok) throw new Error('Failed to create node')
  return response.json()
}

export async function updateOrgChartNode(nodeId, updates) {
  const response = await fetch(`${API_BASE}/org-chart-nodes/${nodeId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!response.ok) throw new Error('Failed to update node')
  return response.json()
}

export async function deleteOrgChartNode(nodeId) {
  const response = await fetch(`${API_BASE}/org-chart-nodes/${nodeId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to delete node')
}

export async function createOrgChartEdge(companyId, edge) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/org-chart-edges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edge),
  })
  if (!response.ok) throw new Error('Failed to create edge')
  return response.json()
}

export async function deleteOrgChartEdge(edgeId) {
  const response = await fetch(`${API_BASE}/org-chart-edges/${edgeId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to delete edge')
}
