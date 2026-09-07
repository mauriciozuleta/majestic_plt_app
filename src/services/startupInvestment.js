import { API_BASE } from './apiBase'

export async function fetchStartupInvestmentPlan(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/plan`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error('Failed to load the start-up investment plan')
  return response.json()
}

export async function createStartupInvestmentPlan(companyId, preOperationalMonths) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pre_operational_months: preOperationalMonths }),
  })
  if (!response.ok) throw new Error('Failed to create the start-up investment plan')
  return response.json()
}

export async function updateStartupInvestmentPlan(companyId, preOperationalMonths) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/plan`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pre_operational_months: preOperationalMonths }),
  })
  if (!response.ok) throw new Error('Failed to update the pre-operational months')
  return response.json()
}

export async function fetchStartupInvestmentRecords(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/records`)
  if (!response.ok) throw new Error('Failed to load start-up investment records')
  return response.json()
}

export async function createStartupInvestmentRecord(companyId, record) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/records`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to add the record')
  }
  return response.json()
}

export async function updateStartupInvestmentRecord(companyId, recordId, record) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/records/${recordId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to update the record')
  }
  return response.json()
}

export async function deleteStartupInvestmentRecord(companyId, recordId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/records/${recordId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error('Failed to delete the record')
  return response.json()
}
