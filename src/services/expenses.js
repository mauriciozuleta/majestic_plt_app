import { API_BASE } from './apiBase'

export async function fetchExpenseCategories() {
  const response = await fetch(`${API_BASE}/expense-categories`)
  if (!response.ok) throw new Error('Failed to load expense categories')
  return response.json()
}

export async function fetchExpenses(companyId, year = 0) {
  const params = new URLSearchParams({ year: String(Number(year)) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/expenses?${params.toString()}`)
  if (!response.ok) throw new Error('Failed to load expenses')
  return response.json()
}

export async function saveExpenseEntry(companyId, categoryId, year, months, hardcoded) {
  const params = new URLSearchParams({ year: String(Number(year)) })
  const response = await fetch(`${API_BASE}/companies/${companyId}/expenses/${categoryId}?${params.toString()}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ months, hardcoded }),
  })
  if (!response.ok) throw new Error('Failed to save expense entry')
  return response.json()
}
