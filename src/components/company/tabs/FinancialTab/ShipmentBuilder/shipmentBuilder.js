import { MARKET_PRIORITY } from '../../../../../services/marketOpportunitySettings'

// Shipment builder: the product candidates for one route, from the Market
// Opportunities comparison of the route's origin country (source) against
// its destination country (target).

// Only these opportunity ratings are candidates, in this order; Complex,
// Difficult, Not Viable and unrated products are left out.
export const SHIPMENT_RATINGS = ['Very High', 'High', 'Challenging']
// Every rating, in the scale's order — for a list the user chose themselves
// (the priority list), where nothing is left out.
export const ALL_RATINGS = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable', 'Unrated']

// One entry per source product: a comparison has a row per matched target
// product, so the same source product (e.g. Hot Chili Pepper against five
// Jamaican pepper listings) appears several times — keep its best (lowest)
// Diff %, which also sets its rating.
function bestRowPerProduct(rows) {
  const best = new Map()
  for (const row of rows) {
    const key = `${row.product_name}|${row.hs_code ?? ''}`
    const current = best.get(key)
    if (!current || (row.diff_pct ?? Infinity) < (current.diff_pct ?? Infinity)) best.set(key, row)
  }
  return [...best.values()]
}

// [{ rating, products }] for each of `ratings` that has products.
// Within a rating: a. Country SAM descending (the bigger the target market
// for the product), then b. Diff % ascending (the lower, the larger the
// margin). A missing value always sorts last.
// `extraFor(row)` adds fields to each product (its market level and cargo cap).
export function groupProductsByRating(rows, countrySamFor, ratings = SHIPMENT_RATINGS, extraFor = null) {
  const products = bestRowPerProduct(rows)
    .filter((row) => ratings.includes(row.opportunity_rating || 'Unrated'))
    .map((row) => ({
      key: `${row.product_name}|${row.hs_code ?? ''}`,
      hsCode: row.hs_code,
      productName: row.product_name,
      targetProductName: row.target_product_name,
      diffPct: row.diff_pct,
      opportunityRating: row.opportunity_rating || 'Unrated',
      countrySam: countrySamFor(row),
      ...(extraFor ? extraFor(row) : {}),
    }))
    .sort(
      (a, b) =>
        (b.countrySam ?? -Infinity) - (a.countrySam ?? -Infinity) || (a.diffPct ?? Infinity) - (b.diffPct ?? Infinity),
    )
  return ratings.map((rating) => ({ rating, products: products.filter((item) => item.opportunityRating === rating) })).filter(
    (group) => group.products.length > 0,
  )
}

// Most a product can get: one with a known Country SAM, or one whose market
// size couldn't be defined.
export const SAM_CAP_KG = 1500
export const NO_SAM_CAP_KG = 200

// Spreads `budget` kg over `items` (each with a `cap`) as evenly as the caps allow: one common cap `level`, so a product below it
// keeps its own cap and the kilos it doesn't use go to the others. -> Map(item -> exact kg)
function waterFill(items, budget) {
  const result = new Map()
  let left = Math.max(0, budget)
  const byCap = [...items].sort((a, b) => a.cap - b.cap)
  byCap.forEach((item, index) => {
    const level = left / (byCap.length - index)
    const kg = Math.min(item.cap, level)
    result.set(item, kg)
    left -= kg
  })
  return result
}

// Distributes `capacityKg` over ALL the products (every product in the selection ships), in this order:
//   1. the wholesalers: every one gets its full cap;
//   2. the premium products: every one gets its full cap;
//   3. the niche products (and any product with no market level): they split what is left evenly, none above its own cap.
// A product's cap is its market's Cargo Cap (Settings ▸ Market Opportunity settings ▸ Destination Market, `capKg`), or
// SAM_CAP_KG / NO_SAM_CAP_KG when that isn't set. When the aircraft can't take the full caps, the last group to be served gives
// way: the premium and niche products share what the wholesalers leave evenly (so nobody is dropped), and only if the wholesalers
// alone are too much do all of them come down to one common cap. Cargo left after every cap is the Available P/L.
// `fixedKg` (product key -> kg) holds weights the user typed in by hand (Details ▸ Edit): they are kept as they are, flagged
// `manual`, and come off the capacity first. Whole kg, never above capacity; the kilos lost to rounding go to the first products
// in that order (then Country SAM, then Diff %) that are still under their cap.
// -> { items: [{ ...product, kg, sharePct, manual }], allocatedKg, unallocatedKg }
export function allocateShipment(products, capacityKg, fixedKg = new Map()) {
  const rank = (item) => {
    const index = MARKET_PRIORITY.indexOf(item.marketKey)
    return index === -1 ? MARKET_PRIORITY.length : index
  }
  const capOf = (item) => item.capKg ?? (item.countrySam > 0 ? SAM_CAP_KG : NO_SAM_CAP_KG)
  const manualItems = products.filter((item) => fixedKg.has(item.key)).map((item) => ({ ...item, kg: Math.floor(fixedKg.get(item.key)), manual: true }))
  const budget = Math.max(0, capacityKg - manualItems.reduce((sum, item) => sum + item.kg, 0))
  const ordered = products
    .filter((item) => !fixedKg.has(item.key))
    .map((item) => ({ ...item, cap: capOf(item), manual: false }))
    .sort(
      (a, b) =>
        rank(a) - rank(b) || (b.countrySam ?? -Infinity) - (a.countrySam ?? -Infinity) || (a.diffPct ?? Infinity) - (b.diffPct ?? Infinity),
    )
  const sumCaps = (list) => list.reduce((sum, item) => sum + item.cap, 0)
  const [WHOLESALERS, PREMIUM] = MARKET_PRIORITY
  const wholesalers = ordered.filter((item) => item.marketKey === WHOLESALERS)
  const premium = ordered.filter((item) => item.marketKey === PREMIUM)
  const niche = ordered.filter((item) => item.marketKey !== WHOLESALERS && item.marketKey !== PREMIUM)
  const exact = new Map()
  const give = (list, kgFor) => list.forEach((item) => exact.set(item, kgFor(item)))
  const afterWholesalers = budget - sumCaps(wholesalers)
  if (afterWholesalers <= 0) {
    // the wholesalers alone fill the aircraft: everyone comes down to one common cap
    waterFill(ordered, budget).forEach((kg, item) => exact.set(item, kg))
  } else {
    give(wholesalers, (item) => item.cap)
    const afterPremium = afterWholesalers - sumCaps(premium)
    if (afterPremium >= 0) {
      give(premium, (item) => item.cap)
      waterFill(niche, afterPremium).forEach((kg, item) => exact.set(item, kg))
    } else {
      // the premium caps don't fit after the wholesalers: premium and niche share what is left evenly
      waterFill([...premium, ...niche], afterWholesalers).forEach((kg, item) => exact.set(item, kg))
    }
  }
  // whole kg: round down, then hand the kilos lost to rounding back, in order, to products under their cap
  const sized = ordered.map((item) => ({ ...item, kg: Math.floor(exact.get(item) ?? 0) }))
  let leftover = Math.min(budget, Math.round(ordered.reduce((sum, item) => sum + (exact.get(item) ?? 0), 0))) - sized.reduce((sum, item) => sum + item.kg, 0)
  for (const item of sized) {
    if (leftover <= 0) break
    if (item.kg < item.cap) {
      item.kg += 1
      leftover -= 1
    }
  }
  const items = [...manualItems, ...sized.filter((item) => item.kg > 0).map(({ cap: _cap, ...product }) => product)]
  const allocatedKg = items.reduce((sum, item) => sum + item.kg, 0)
  return {
    items: items.map((item) => ({ ...item, sharePct: allocatedKg ? (item.kg / allocatedKg) * 100 : 0 })).sort((a, b) => b.kg - a.kg),
    allocatedKg,
    unallocatedKg: Math.max(0, Math.round(capacityKg - allocatedKg)),
  }
}
