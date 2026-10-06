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

// Market Level: the Destination Market category whose from/to range (in %) holds the DDP price as a % of the target price.
// An empty end of a range is open. -> { level, key, share, configured, cargoCapKg } — `level`/`key` are null when no category matches / none is set.
export function marketLevelFor(ddpPerKg, targetPricePerKg, markets) {
  if (ddpPerKg == null || !targetPricePerKg) return { level: null, key: null, share: null, configured: false, cargoCapKg: null }
  const share = (ddpPerKg / targetPricePerKg) * 100
  const configured = (markets || []).filter((market) => market.min != null || market.max != null)
  const match = configured.find((market) => share >= (market.min ?? -Infinity) && share <= (market.max ?? Infinity))
  return { level: match?.label ?? null, key: match?.key ?? null, share, configured: configured.length > 0, cargoCapKg: match?.cargo_cap_kg ?? null }
}

// Shipment builder order: wholesalers get their Cargo Cap first, then premium theirs, and the niche markets share what is left.
export const MARKET_PRIORITY = ['wholesalers', 'premium', 'niche']
// A product with no match in the target market (no target price to compare) is a niche market product by definition.
export const UNMATCHED_MARKET_KEY = 'niche'

// Suggested sell price per kg of a product, by its market level (Settings ▸ Destination Market, `sell_pct`):
//   wholesalers -> sell_pct % of the target price (60 = 60 % of what the target market pays);
//   niche / premium -> the DDP price plus sell_pct % profit (20 = DDP x 1.20).
// -> { value, note } — value is null when what the rule needs is missing.
export function suggestedSellPrice(marketKey, ddpPerKg, targetPricePerKg, markets) {
  const market = (markets || []).find((item) => item.key === marketKey)
  if (!market) return { value: null, note: '' }
  if (market.sell_pct == null) return { value: null, note: `Set the sell price % of ${market.label} in Settings ▸ Market Opportunity settings ▸ Destination Market.` }
  if (marketKey === 'wholesalers') {
    return targetPricePerKg
      ? { value: (targetPricePerKg * market.sell_pct) / 100, note: `${market.sell_pct}% of the target price` }
      : { value: null, note: 'Needs the target price' }
  }
  return ddpPerKg != null ? { value: ddpPerKg * (1 + market.sell_pct / 100), note: `DDP price + ${market.sell_pct}% profit` } : { value: null, note: 'Needs the DDP price' }
}
