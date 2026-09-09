// General Portfolio Directory — every distinct product name across every
// country's product portfolio, deduplicated (the same product sourced from
// 3 countries appears once), alphabetized, with a reference code. Recomputed
// fresh from the live snapshot data each time it's needed — deliberately
// not cached/persisted, since that's the simplest way to keep it "always
// current" without a separate update-trigger mechanism. Shared (not tab-
// specific) because three places need it: Documentation's own directory
// listing, and each country's own Product Analysis table showing its own
// products' codes.
//
// Built on the frontend, not the backend, because product names need to be
// in English for this to be useful as a single cross-country reference —
// Colombia's raw data is Spanish, and the Spanish->English dictionary
// (productTranslations.js) is a frontend-only concern by design (see its
// own header comment). Duplicating that dictionary server-side would be a
// second copy that could drift from the real one.

import { mergeSources } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData'
import { translateProductName } from '../components/company/tabs/OperationsTab/MarketAnalysis/productTranslations'
import { fetchPriceComparisonSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'

// Same category concept gets the same 2-letter code regardless of which
// country/source uses which name for it (Colombia's "Carnicos" and the
// USA's "Beef" both become "BE") — chosen to avoid collisions between
// genuinely different categories (Pork "PK" vs Poultry "PO").
const CATEGORY_CODES = {
  pollo: { code: 'PO', label: 'Poultry' },
  pescados_mariscos: { code: 'FI', label: 'Fish & Seafood' },
  platanos: { code: 'PL', label: 'Plantains' },
  tuberculos: { code: 'TU', label: 'Tubers' },
  frutas: { code: 'FR', label: 'Fruits' },
  hortalizas: { code: 'VE', label: 'Vegetables' },
  carnicos: { code: 'BE', label: 'Beef' },
  huevos: { code: 'EG', label: 'Eggs' },
  lacteos: { code: 'DA', label: 'Dairy' },
  granos_procesados: { code: 'GR', label: 'Grains & Processed' },
  Beef: { code: 'BE', label: 'Beef' },
  Pork: { code: 'PK', label: 'Pork' },
  Poultry: { code: 'PO', label: 'Poultry' },
  Eggs: { code: 'EG', label: 'Eggs' },
  'Grains (Export)': { code: 'GR', label: 'Grains (Export)' },
  'Produce (FL Shipping Point)': { code: 'PF', label: 'Produce (FL)' },
  'Produce (CA Shipping Point)': { code: 'PC', label: 'Produce (CA)' },
}

function categoryInfo(rawCategory) {
  if (CATEGORY_CODES[rawCategory]) return CATEGORY_CODES[rawCategory]
  const letters = (rawCategory || '').replace(/[^A-Za-z]/g, '').toUpperCase()
  return { code: letters.slice(0, 2) || 'XX', label: rawCategory || 'Uncategorized' }
}

async function collectColombiaProducts() {
  const snapshots = await fetchPriceComparisonSnapshot()
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  if (!bySource.la_mayorista && !bySource.corabastos) return []
  const merged = mergeSources(bySource.la_mayorista || [], bySource.corabastos || [])
  return merged.map((p) => ({ name: translateProductName(p.nameEs).text, category: p.category }))
}

async function collectUsaProducts() {
  const snapshots = await fetchUsaSourcingSnapshot()
  return snapshots.flatMap((s) => s.products).map((p) => ({ name: p.product_en, category: p.category }))
}

// Each real product-portfolio source (only Colombia and the USA exist as
// real pipelines today) contributes {countryName, products}. Extending to
// a future country's portfolio is just adding another entry here.
async function collectAllSources() {
  const [colombia, usa] = await Promise.all([
    collectColombiaProducts().catch(() => []),
    collectUsaProducts().catch(() => []),
  ])
  return [
    { countryName: 'Colombia', products: colombia },
    { countryName: 'United States', products: usa },
  ]
}

export async function buildProductPortfolio(countryCodeByName) {
  const sources = await collectAllSources()

  const byKey = new Map()
  sources.forEach(({ countryName, products }) => {
    products.forEach(({ name, category }) => {
      const trimmed = (name || '').trim()
      if (!trimmed) return
      const key = trimmed.toLowerCase()
      if (!byKey.has(key)) {
        byKey.set(key, { name: trimmed, category, countries: [] })
      }
      const entry = byKey.get(key)
      if (!entry.countries.includes(countryName)) entry.countries.push(countryName)
    })
  })

  const rows = Array.from(byKey.values()).sort((a, b) => a.name.localeCompare(b.name))

  return rows.map((row, index) => {
    const primaryCountry = row.countries[0]
    const countryCode = countryCodeByName.get(primaryCountry.toLowerCase()) || 'XX'
    const { code: categoryCode, label: categoryLabel } = categoryInfo(row.category)
    const sequence = String(index + 1).padStart(3, '0')
    return {
      code: `${countryCode}${categoryCode}${sequence}`,
      name: row.name,
      category: categoryLabel,
      countries: row.countries,
    }
  })
}

/** Convenience for a single country's Product Analysis table: the same
 * portfolio, as a lookup from normalized (lowercase, trimmed) product name
 * straight to its code — so a table doesn't need to hold the whole
 * portfolio just to look up its own rows' codes. */
export async function buildProductCodeIndex(countryCodeByName) {
  const portfolio = await buildProductPortfolio(countryCodeByName)
  return new Map(portfolio.map((row) => [row.name.toLowerCase(), row.code]))
}
