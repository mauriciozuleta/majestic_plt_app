// Providers per expense category (backend/routers/expense_providers.py):
// those added by hand plus every provider already named on a saved expense.
import { API_BASE } from './apiBase'

// [{ category, providers: [{ name, source: 'manual' | 'expense', expense_count }] }]
export async function fetchExpenseProviders(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/expense-providers`)
  if (!response.ok) throw new Error('Failed to load providers')
  return response.json()
}

export async function createExpenseProvider(companyId, categoryName, name) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/expense-providers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_name: categoryName, name }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Could not save the provider')
  }
  return response.json()
}

// Provider names for one expense category, matched case-insensitively.
export function providersForCategory(groups, categoryName) {
  const key = (categoryName || '').trim().toLowerCase()
  return groups.find((group) => group.category.trim().toLowerCase() === key)?.providers ?? []
}
