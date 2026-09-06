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

export async function fetchStartupInvestmentEntries(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/entries`)
  if (!response.ok) throw new Error('Failed to load start-up investment entries')
  return response.json()
}

export async function saveStartupInvestmentEntry(companyId, category, months) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/startup-investment/entries/${category}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ months }),
  })
  if (!response.ok) throw new Error('Failed to save start-up investment entry')
  return response.json()
}
