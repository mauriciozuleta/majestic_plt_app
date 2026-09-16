import { API_BASE } from './apiBase'

async function readErrorDetail(response, fallbackMessage) {
  try {
    const payload = await response.json()
    if (payload?.detail) return payload.detail
  } catch {
    // Ignore parse errors and use fallback message.
  }
  return fallbackMessage
}

export async function fetchRiskAnalysis(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/risk-analysis`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load risk analysis'))
  return response.json()
}

export async function createRiskCategory(companyId, name) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/risk-categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to create category'))
  return response.json()
}

export async function updateRiskCategory(categoryId, name) {
  const response = await fetch(`${API_BASE}/risk-categories/${categoryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to rename category'))
  return response.json()
}

export async function deleteRiskCategory(categoryId) {
  const response = await fetch(`${API_BASE}/risk-categories/${categoryId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to delete category'))
  return response.json()
}

export async function createRisk(categoryId, payload) {
  const response = await fetch(`${API_BASE}/risk-categories/${categoryId}/risks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to create risk'))
  return response.json()
}

export async function updateRisk(riskId, payload) {
  const response = await fetch(`${API_BASE}/risks/${riskId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update risk'))
  return response.json()
}

export async function deleteRisk(riskId) {
  const response = await fetch(`${API_BASE}/risks/${riskId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to delete risk'))
  return response.json()
}

export async function createMechanism(riskId, payload) {
  const response = await fetch(`${API_BASE}/risks/${riskId}/mechanisms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to create mechanism'))
  return response.json()
}

export async function updateMechanism(mechanismId, payload) {
  const response = await fetch(`${API_BASE}/mechanisms/${mechanismId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to update mechanism'))
  return response.json()
}

export async function deleteMechanism(mechanismId) {
  const response = await fetch(`${API_BASE}/mechanisms/${mechanismId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to delete mechanism'))
  return response.json()
}

export async function startRiskPlan(companyId, categoryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/risk-categories/${categoryId}/generate-plan`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to start plan generation'))
  return response.json()
}

export async function fetchRiskPlan(companyId, categoryId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/risk-categories/${categoryId}/plan`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load the plan'))
  return response.json()
}
