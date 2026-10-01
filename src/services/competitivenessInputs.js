import { fetchPriceComparisonSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { mergeSources } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData'
import { fetchCustomSourceProducts } from './productSources'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'

// Builds the {category, avg_price, unit, product_count, sample_products}
// summary the backend prompt needs — computed here, not on the backend,
// since each source's product shape differs (Colombia's is a two-source
// merge, USA's is a flat per-report list) and the frontend already knows
// how to read both correctly (see ColombiaProductAnalysisView/
// USASourcingView).
async function buildColombiaCategorySummary() {
  const snapshots = await fetchPriceComparisonSnapshot()
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  const merged = mergeSources(bySource.la_mayorista || [], bySource.corabastos || [])
  return summarizeByCategory(
    merged.map((p) => ({
      category: p.category,
      price: p.laMayorista ?? p.corabastos,
      unit: 'COP',
      name: p.nameEs,
    })),
  )
}

async function buildUsaCategorySummary() {
  const snapshots = await fetchUsaSourcingSnapshot()
  const products = snapshots.flatMap((s) => s.products)
  return summarizeByCategory(products.map((p) => ({ category: p.category, price: p.price, unit: p.unit, name: p.product_en })))
}

function summarizeByCategory(rows) {
  const byCategory = new Map()
  rows.forEach((row) => {
    if (row.price == null || !row.category) return
    if (!byCategory.has(row.category)) byCategory.set(row.category, { prices: [], names: [], unit: row.unit })
    const bucket = byCategory.get(row.category)
    bucket.prices.push(row.price)
    bucket.names.push(row.name)
  })
  return Array.from(byCategory.entries()).map(([category, bucket]) => ({
    category,
    avg_price: Math.round((bucket.prices.reduce((sum, v) => sum + v, 0) / bucket.prices.length) * 100) / 100,
    unit: bucket.unit,
    product_count: bucket.prices.length,
    sample_products: Array.from(new Set(bucket.names)).slice(0, 5),
  }))
}

// Countries other than Colombia/USA get their summary from the sources added
// in Settings. Prices stay in the source's own unit and currency (shown in
// the unit label), since there's no conversion table for arbitrary sources.
async function buildCustomCategorySummary(countryNameLower) {
  const sources = (await fetchCustomSourceProducts()).filter((s) => s.country_name.trim().toLowerCase() === countryNameLower)
  const rows = sources.flatMap((source) =>
    source.products.map((p) => ({
      category: p.category,
      price: p.price,
      unit: [p.currency, p.unit && `per ${p.unit}`].filter(Boolean).join(' '),
      name: p.name,
    })),
  )
  return rows.length ? summarizeByCategory(rows) : null
}

// A country's built-in pipeline (Colombia/USA) and any sources added for it in
// Settings are combined, never one in place of the other. Each is summarized
// separately so a category's average never mixes units or currencies.
export async function getCategorySummary(countryName) {
  const name = countryName.trim().toLowerCase()
  const builtIn = name === 'colombia' ? buildColombiaCategorySummary() : name === 'united states' ? buildUsaCategorySummary() : null
  const [builtInSummary, customSummary] = await Promise.all([builtIn, buildCustomCategorySummary(name)])
  if (!builtInSummary) return customSummary
  return customSummary ? [...builtInSummary, ...customSummary] : builtInSummary
}
