// Independent currency-conversion module — not tied to any one feature.
// Wraps GET /api/exchange-rate/, which the backend serves from a
// standalone utility (backend/currency/exchange_rate.py) independent of
// any one router. Any screen needing a live FX rate can import this.

import { API_BASE } from './apiBase'

export async function fetchExchangeRate(fromCurrency, toCurrency = 'USD') {
  const params = new URLSearchParams({ from: fromCurrency, to: toCurrency })
  const response = await fetch(`${API_BASE}/api/exchange-rate/?${params.toString()}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
