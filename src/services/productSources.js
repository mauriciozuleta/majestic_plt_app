import { API_BASE } from './apiBase'

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// { built_in: [...], custom: [...] } — built-in sources are the code-defined
// Colombia/USA pipelines (display only); custom ones are the user's own.
export const fetchProductSources = () => request('/product-sources')

// Adding (or changing the address of) a source with a web address analyses
// the site straight away, so these can take a while.
export const createProductSource = (payload) => request('/product-sources', json('POST', payload))
export const updateProductSource = (id, payload) => request(`/product-sources/${id}`, json('PUT', payload))
// Works for both a custom source and a built-in one (La Mayorista,
// Corabastos, the USDA feeds) — built-ins have no other editable fields,
// so this is their only way to flip Wholesaler/Retail (see
// backend/routers/product_sources.py's set_analysis_type).
export const setSourceAnalysisType = (id, analysisType) =>
  request(`/product-sources/${id}/analysis-type`, json('PUT', { analysis_type: analysisType }))
export const refreshProductSource = (id) => request(`/product-sources/${id}/refresh`, { method: 'POST' })
export const deleteProductSource = (id) => request(`/product-sources/${id}`, { method: 'DELETE' })

export const loadProductSourceFile = async (id, file) => {
  const contentBase64 = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(new Error('Could not read the selected file.'))
    reader.readAsDataURL(file)
  })
  return request(`/product-sources/${id}/file`, json('POST', { filename: file.name, content_base64: contentBase64 }))
}

// Every custom source that has products: [{ source_id, source_name, country_name, currency, fetched_at, products }]
export const fetchCustomSourceProducts = () => request('/product-sources/products')
