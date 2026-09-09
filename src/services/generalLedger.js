import { API_BASE } from './apiBase'

export async function fetchChartOfAccounts(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/gl/accounts`)
  if (!response.ok) throw new Error('Failed to load chart of accounts')
  return response.json()
}

export async function fetchJournalEntries(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/gl/journal-entries`)
  if (!response.ok) throw new Error('Failed to load journal entries')
  return response.json()
}
