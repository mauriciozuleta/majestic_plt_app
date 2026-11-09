// Live source fetchers for the USA sourcing module — seven independent
// USDA AMS reports (Beef, Pork, Poultry, Eggs, Grains, Produce FL, Produce
// CA). Each request is independent: one report being unavailable never
// blocks the others from loading. No polling/scheduling — this only ever
// runs from the Update button. No Seafood fetcher: no confirmed primary
// source was identified for it (see the module spec's open items).

import { API_BASE } from '../../../../../services/apiBase'

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const USA_SOURCES = [
  { key: 'beef', label: 'Beef', path: '/market-analysis/usa/beef' },
  { key: 'pork', label: 'Pork', path: '/market-analysis/usa/pork' },
  { key: 'poultry', label: 'Poultry', path: '/market-analysis/usa/poultry' },
  { key: 'eggs', label: 'Eggs', path: '/market-analysis/usa/eggs' },
  { key: 'grains', label: 'Grains (Export)', path: '/market-analysis/usa/grains' },
  { key: 'produce_fl', label: 'Produce (FL)', path: '/market-analysis/usa/produce-fl' },
  { key: 'produce_ca', label: 'Produce (CA)', path: '/market-analysis/usa/produce-ca' },
  // USDA My Market News API (MARS): national retail prices of fruit and vegetables, one store-weighted average row per commodity
  { key: 'retail_produce', label: 'Retail Produce (MARS)', path: '/market-analysis/usa/retail-produce' },
]

// A source can also store its DETAIL rows (the retail report's individual packs, which the catalog normalization module averages into one row per
// commodity): the rest of the app only ever sees the rows that are not detail.
const withoutDetail = (products) => (Array.isArray(products) ? products.filter((product) => !product.detail) : products)

export async function fetchUsaSourceProducts(sourceKey) {
  const source = USA_SOURCES.find((s) => s.key === sourceKey)
  return withoutDetail(await fetchJson(source.path))
}

export async function fetchUsaSourcingSnapshot() {
  const snapshots = await fetchJson('/market-analysis/usa/snapshot')
  return snapshots.map((snapshot) => ({ ...snapshot, products: withoutDetail(snapshot.products) }))
}
