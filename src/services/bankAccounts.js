import { API_BASE } from './apiBase'

// Bank names are free-typed, so the same bank can end up stored with
// slightly different casing/spacing across accounts (e.g. "Bank of America"
// vs "bank of  america") — normalize before comparing/grouping so those
// still count as the same bank, without ever rewriting what was typed.
export function normalizeBankName(name) {
  return (name || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

async function readErrorDetail(response, fallbackMessage) {
  try {
    const payload = await response.json()
    if (payload?.detail) return payload.detail
  } catch {
    // Ignore parse errors and use fallback message.
  }
  return fallbackMessage
}

export async function fetchBankAccounts(companyId) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/bank-accounts`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load bank accounts'))
  return response.json()
}

export async function createBankAccount(companyId, payload) {
  const response = await fetch(`${API_BASE}/companies/${companyId}/bank-accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to create bank account'))
  return response.json()
}

export async function deleteBankAccount(accountId) {
  const response = await fetch(`${API_BASE}/bank-accounts/${accountId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to delete bank account'))
  return response.json()
}

export async function fetchBankTransactions(accountId) {
  const response = await fetch(`${API_BASE}/bank-accounts/${accountId}/transactions`)
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to load transactions'))
  return response.json()
}

export async function createBankTransfer(payload) {
  const response = await fetch(`${API_BASE}/bank-accounts/transfer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readErrorDetail(response, 'Failed to create transfer'))
  return response.json()
}
