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

export async function renameExpenseCategory(categoryId, name, percentOfEnabled = false, percentOfMetric = null) {
  const response = await fetch(`${API_BASE}/expense-categories/${categoryId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, percent_of_enabled: percentOfEnabled, percent_of_metric: percentOfMetric }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to rename expense category')
  }
  return response.json()
}

export async function fetchExpenseCategoryCompanySettings() {
  const response = await fetch(`${API_BASE}/expense-category-company-settings`)
  if (!response.ok) throw new Error('Failed to load expense company settings')
  return response.json()
}

export async function setExpenseCategoryCompanySetting(categoryId, companyId, excluded, percentValue) {
  const response = await fetch(`${API_BASE}/expense-category-company-settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_id: categoryId, company_id: companyId, excluded, percent_value: percentValue }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail || 'Failed to update expense company setting')
  }
  return response.ok
}
