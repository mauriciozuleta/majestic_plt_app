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

export async function createExpenseCategory(name) {
  const response = await fetch(`${API_BASE}/expense-categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to create expense category')
  }
  return response.json()
}

export async function deleteExpenseCategory(categoryId) {
  const response = await fetch(`${API_BASE}/expense-categories/${categoryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to delete expense category')
  }
  return response.json()
}

export async function renameExpenseCategory(categoryId, name) {
  const response = await fetch(`${API_BASE}/expense-categories/${categoryId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to rename expense category')
  }
  return response.json()
}

export async function fetchExpenseCategoryExclusions() {
  const response = await fetch(`${API_BASE}/expense-category-country-exclusions`)
  if (!response.ok) throw new Error('Failed to load expense country settings')
  return response.json()
}

export async function setExpenseCategoryApplicability(categoryId, countryId, applicable) {
  const response = await fetch(`${API_BASE}/expense-category-country-exclusions`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_id: categoryId, country_id: countryId, applicable }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to update expense country setting')
  }
  return response.ok
}
