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
export function groupProductsByRating(rows, countrySamFor, ratings = SHIPMENT_RATINGS) {
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

// How strongly a product draws on the cargo: market size (Country SAM, on a
// log scale across the selection, 0.2–1) times margin ((100 − Diff %) / 100,
// 0.05–1; 0.5 when unknown). A product with no SAM draws only 0.1 × margin.
function allocationWeights(products) {
  const logs = products.filter((item) => item.countrySam > 0).map((item) => Math.log10(item.countrySam))
  const minLog = Math.min(...logs)
  const maxLog = Math.max(...logs)
  const margin = (item) => (item.diffPct == null ? 0.5 : Math.min(1, Math.max(0.05, (100 - item.diffPct) / 100)))
  return products.map((item) => {
    if (!(item.countrySam > 0)) return 0.1 * margin(item)
    const size = maxLog > minLog ? 0.2 + (0.8 * (Math.log10(item.countrySam) - minLog)) / (maxLog - minLog) : 1
    return size * margin(item)
  })
}

// Distributes `capacityKg` across the selected products by weight, never past
// a product's cap: whatever a capped product can't take goes back to the
// rest, until the cargo or every cap runs out. Whole kg, never above
// capacity. -> { items: [{ ...product, kg, sharePct }], allocatedKg, unallocatedKg }
export function allocateShipment(products, capacityKg) {
  const weights = allocationWeights(products)
  const items = products.map((item, index) => ({ ...item, cap: item.countrySam > 0 ? SAM_CAP_KG : NO_SAM_CAP_KG, weight: weights[index], exact: 0 }))
  let remaining = capacityKg
  let open = items.filter((item) => item.weight > 0)
  while (open.length && remaining > 0.5) {
    const total = open.reduce((sum, item) => sum + item.weight, 0)
    const capped = open.filter((item) => (remaining * item.weight) / total >= item.cap - item.exact)
    if (!capped.length) {
      open.forEach((item) => {
        item.exact += (remaining * item.weight) / total
      })
      remaining = 0
      break
    }
    capped.forEach((item) => {
      remaining -= item.cap - item.exact
      item.exact = item.cap
    })
    open = open.filter((item) => !capped.includes(item))
  }
  // Whole kg: round everything down, then hand the kilos lost to rounding back
  // one at a time to the products that lost the most — so only the product
  // limits, never rounding, can leave cargo unallocated.
  items.forEach((item) => {
    item.kg = Math.floor(item.exact)
  })
  let leftover = Math.round(items.reduce((sum, item) => sum + item.exact, 0)) - items.reduce((sum, item) => sum + item.kg, 0)
  const byFraction = [...items].filter((item) => item.kg < item.cap).sort((a, b) => b.exact - b.kg - (a.exact - a.kg))
  for (const item of byFraction) {
    if (leftover <= 0) break
    item.kg += 1
    leftover -= 1
  }
  const allocatedKg = items.reduce((sum, item) => sum + item.kg, 0)
  return {
    items: items
      .map((item) => {
        const { cap: _cap, weight: _weight, exact: _exact, ...product } = item
        return product
      })
      .map((item) => ({ ...item, sharePct: allocatedKg ? (item.kg / allocatedKg) * 100 : 0 }))
      .sort((a, b) => b.kg - a.kg),
    allocatedKg,
    unallocatedKg: Math.max(0, Math.round(capacityKg - allocatedKg)),
  }
}
