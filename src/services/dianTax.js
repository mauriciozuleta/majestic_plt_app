import { API_BASE } from './apiBase'

// Colombia (DIAN WebArancel) Gravamen + IVA lookups — backend/routers/tax_calculator.py, backend/tax_calc/colombia_dian/.
// A lookup takes ~5-20 s, so it runs as a background job: start it, then poll its progress.

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// -> { jobId }
export const startDianLookup = ({ hsCode, date, forceRefresh = false, debug = false }) =>
  request('/tax-calc/colombia/dian/lookups', json('POST', { hsCode, date: date || null, forceRefresh, debug }))

// -> { id, status: 'running' | 'done', progress: [{ step, message }], result: TaxLookupResult | null }
export const fetchDianJob = (jobId) => request(`/tax-calc/colombia/dian/jobs/${encodeURIComponent(jobId)}`)

// { customsValue, gravamen: TaxValue | null, iva: TaxValue | null, ivaStatus } -> the calculation with every intermediate figure
export const calculateDianTaxes = (payload) => request('/tax-calc/colombia/dian/calculate', json('POST', payload))

export const DIAN_STEPS = [
  { key: 'connecting', label: 'Connecting to DIAN' },
  { key: 'searching', label: 'Searching nomenclature' },
  { key: 'resolving', label: 'Resolving tariff code' },
  { key: 'gravamen', label: 'Reading Gravamen' },
  { key: 'iva', label: 'Reading IVA' },
  { key: 'complete', label: 'Complete' },
]
