import { colombiaPricePerKg } from './unitConversion'

export const CANONICAL_CATEGORIES = [
  { key: 'pollo', es: 'Pollo', en: 'Poultry' },
  { key: 'pescados_mariscos', es: 'Pescados y Mariscos', en: 'Fish & Seafood' },
  { key: 'platanos', es: 'Platanos', en: 'Plantains' },
  { key: 'tuberculos', es: 'Tuberculos', en: 'Tubers' },
  { key: 'frutas', es: 'Frutas', en: 'Fruits' },
  { key: 'hortalizas', es: 'Hortalizas', en: 'Vegetables' },
  { key: 'carnicos', es: 'Carnicos', en: 'Beef' },
  { key: 'huevos', es: 'Huevos', en: 'Eggs' },
  { key: 'lacteos', es: 'Lacteos', en: 'Dairy' },
  { key: 'granos_procesados', es: 'Granos y Procesados', en: 'Grains & Processed' },
]

/** Full outer join of the two source lists by product id (§3: every product
 * from either source must appear, matched or not — never an inner join).
 * The shared `id` is what the backend's curated match table (see
 * backend/price_sources/match_table.py) produces by rewriting one source's
 * product id to the other's when they're the same real product under a
 * different name. */
export function mergeSources(laMayoristaProducts, corabastosProducts) {
  const byId = new Map()

  laMayoristaProducts.forEach((product) => {
    byId.set(product.id, {
      ...product,
      laMayorista: product.price,
      laMayoristaUnit: product.unit,
      laMayoristaUnitLabel: product.unitLabel || null,
      corabastos: null,
      corabastosUnit: null,
      corabastosUnitLabel: null,
    })
  })
  corabastosProducts.forEach((product) => {
    const existing = byId.get(product.id)
    if (existing) {
      existing.corabastos = product.price
      existing.corabastosUnit = product.unit
      existing.corabastosUnitLabel = product.unitLabel || null
    } else {
      byId.set(product.id, {
        ...product,
        laMayorista: null,
        laMayoristaUnit: null,
        laMayoristaUnitLabel: null,
        corabastos: product.price,
        corabastosUnit: product.unit,
        corabastosUnitLabel: product.unitLabel || null,
      })
    }
  })

  return Array.from(byId.values()).map((product) => {
    const laMayoristaPerKg = colombiaPricePerKg(product.laMayorista, product.laMayoristaUnit, product.laMayoristaUnitLabel)
    const corabastosPerKg = colombiaPricePerKg(product.corabastos, product.corabastosUnit, product.corabastosUnitLabel)
    const matched = product.laMayorista != null && product.corabastos != null
    const sourceTag = matched ? null : product.laMayorista != null ? 'La Mayorista only' : 'Corabastos only'
    // Comparable once BOTH sides resolve to a real $/kg price — broader than
    // "both sides literally say kg", since e.g. a libra-priced La Mayorista
    // row and a kg-priced Corabastos row both convert to the same unit and
    // are genuinely comparable once normalized.
    const comparable = laMayoristaPerKg !== null && corabastosPerKg !== null
    const diffPct = comparable ? ((corabastosPerKg - laMayoristaPerKg) / laMayoristaPerKg) * 100 : null
    const isOutlier = comparable && Math.abs(diffPct) > 100
    const cheaperAt = comparable ? (laMayoristaPerKg < corabastosPerKg ? 'la_mayorista' : 'corabastos') : null
    const unitLabel = product.corabastosUnitLabel || product.laMayoristaUnitLabel || null

    // A short per-side unit summary for the Unit column — "kg" when a side
    // reports a genuine per-kilo price, otherwise its package descriptor
    // (e.g. "BULTO (50 per package)"), omitting a side that has no data.
    const unitParts = []
    if (product.laMayorista != null) {
      unitParts.push(`LM: ${product.laMayoristaUnit === 'kg' ? 'kg' : product.laMayoristaUnitLabel || 'other'}`)
    }
    if (product.corabastos != null) {
      unitParts.push(`CB: ${product.corabastosUnit === 'kg' ? 'kg' : product.corabastosUnitLabel || 'other'}`)
    }
    const unitDisplay = matched && comparable ? 'kg (both)' : unitParts.join(' · ')

    return {
      ...product,
      laMayoristaPerKg,
      corabastosPerKg,
      matched,
      sourceTag,
      comparable,
      diffPct,
      isOutlier,
      cheaperAt,
      unitLabel,
      unitDisplay,
    }
  })
}
