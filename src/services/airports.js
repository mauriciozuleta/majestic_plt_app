import { API_BASE } from './apiBase'

export async function lookupAirportByIata(iataCode) {
  const response = await fetch(`${API_BASE}/airport-lookup?iata_code=${encodeURIComponent(iataCode)}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Airport not found')
  }
  return response.json()
}
