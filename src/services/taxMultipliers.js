import { API_BASE } from './apiBase'

// Import-tax multipliers of a portfolio's products for an origin -> destination pair
// (backend/routers/tax_calculator.py, tax_calc/mapping.py).

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const productKey = (name) => (name || '').trim().toLowerCase()

// products: [{ name, hsCode, category, priceUsdPerKg }] -> { destination, origin, products, by_status }
export const computeTaxMultipliers = (destination, origin, products) =>
  request(
    '/tax-calc/multipliers/compute',
    json('POST', { destination, origin, products: products.map((p) => ({ name: p.name, hs_code: p.hsCode, category: p.category, price_usd_kg: p.priceUsdPerKg })) }),
  )

// -> Map(productKey -> { tax_multiplier, landed_multiplier, status, method, note, tariff_code, tariff_path, detail }), or an empty map
// when the destination has no calculator yet
export async function fetchTaxMultipliers(destination, origin) {
  const data = await request(`/tax-calc/multipliers?destination=${encodeURIComponent(destination)}&origin=${encodeURIComponent(origin)}`)
  return new Map(data.multipliers.map((row) => [row.product_key, row]))
}

// The destination tariff line a product maps to -> { line, method, status, note, candidates }
export const suggestTariffLine = (destination, { name, hsCode, origin, priceUsdPerKg }) => {
  const params = new URLSearchParams({ name })
  if (hsCode) params.set('hs_code', hsCode)
  if (origin) params.set('origin', origin)
  if (priceUsdPerKg != null) params.set('price_usd_kg', String(priceUsdPerKg))
  return request(`/tax-calc/${encodeURIComponent(destination)}/suggest?${params.toString()}`)
}

// "x2.23" — the taxes as a multiple of the goods value
export const formatMultiplier = (value) => (value == null ? '—' : `x${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
