import { API_BASE } from './apiBase'

// Settings ▸ Market Opportunity settings: { margin_tiers: [{ rating, min, max }], destination_markets: [{ key, label, min, max }] }.
// The margin tiers are the opportunity-rating scale (diff % = source price as a % of the target price) used by the backend
// when it rates a comparison; saving them re-rates every saved comparison.
export async function fetchMarketOpportunitySettings() {
  const response = await fetch(`${API_BASE}/market-opportunity-settings`)
  if (!response.ok) throw new Error('Failed to load the Market Opportunity settings')
  return response.json()
}

export async function saveMarketOpportunitySettings(settings) {
  const response = await fetch(`${API_BASE}/market-opportunity-settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || 'Failed to save the Market Opportunity settings')
  }
  return response.json()
}
