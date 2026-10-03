// Shipment builder: the product candidates for one route, from the Market
// Opportunities comparison of the route's origin country (source) against
// its destination country (target).

// Only these opportunity ratings are candidates, in this order; Complex,
// Difficult, Not Viable and unrated products are left out.
export const SHIPMENT_RATINGS = ['Very High', 'High', 'Challenging']

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

// [{ rating, products }] for each of SHIPMENT_RATINGS that has products.
// Within a rating: a. Country SAM descending (the bigger the target market
// for the product), then b. Diff % ascending (the lower, the larger the
// margin). A missing value always sorts last.
export function groupProductsByRating(rows, countrySamFor) {
  const products = bestRowPerProduct(rows)
    .filter((row) => SHIPMENT_RATINGS.includes(row.opportunity_rating))
    .map((row) => ({
      key: `${row.product_name}|${row.hs_code ?? ''}`,
      hsCode: row.hs_code,
      productName: row.product_name,
      targetProductName: row.target_product_name,
      diffPct: row.diff_pct,
      opportunityRating: row.opportunity_rating,
      countrySam: countrySamFor(row),
    }))
    .sort(
      (a, b) =>
        (b.countrySam ?? -Infinity) - (a.countrySam ?? -Infinity) || (a.diffPct ?? Infinity) - (b.diffPct ?? Infinity),
    )
  return SHIPMENT_RATINGS.map((rating) => ({ rating, products: products.filter((item) => item.opportunityRating === rating) })).filter(
    (group) => group.products.length > 0,
  )
}
