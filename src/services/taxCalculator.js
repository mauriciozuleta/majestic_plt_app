import { API_BASE } from './apiBase'

// Import-tax calculators per country — backend/routers/tax_calculator.py.

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const country = (name) => `/tax-calc/${encodeURIComponent(name)}`

// -> { countries: [{ country, ready, lines, source, data_date, can_refresh, refresh_note, currency }] }
export const fetchTaxCountries = () => request('/tax-calc/countries')

// a product name (words) or a tariff code (digits) -> { lines: [{ code, description, path, units, summary }] }
export const searchTariffLines = (name, query) => request(`${country(name)}/search?q=${encodeURIComponent(query)}&limit=40`)

// { code, price_per_kg_usd + quantity_kg | goods_value_usd, quantity_units, freight_usd, insurance_usd, origin, transport,
//   commercial_importer } -> { line, value_basis, taxes: [{ name, amount, rate, basis, formula, recoverable, note }],
//   total_tax_usd, total_per_kg_usd, total_pct_of_goods, landed_cost_usd, complete, notes, warnings, sources }
export const calculateTax = (name, payload) =>
  request(`${country(name)}/calculate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })

export const refreshTariffData = (name) => request(`${country(name)}/refresh`, { method: 'POST' })
