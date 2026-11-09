// What is left of the per-country unit conversions after the catalog normalization module took them over.
//
// Converting a price to a price per kg is NOT done here any more: it happens once, in the backend (backend/catalog_normalization), when a catalog is stored, and
// every table, the product portfolio and Market Opportunities read the result (src/services/catalogNorm.js). What stays on the frontend is the user's manual
// escape hatch: a price and/or pack weight typed by hand for one exact row, which always wins over the module's figure.

// --- Custom-override row signatures (see src/services/productOverrides.js) ---
//
// A price correction is naturally per exact priced row (a specific product at a specific source, or a specific size grade), so the signature is finer-grained
// than the module's per-product item weights.

export function colombiaRowSignature(category, productName, sourceLabel) {
  return `colombia-row:${category}:${productName.toLowerCase()}:${sourceLabel}`
}

export function usaRowSignature(product) {
  return `usa-row:${product.category}:${product.product_en}:${product.unit}`
}

// Applies a user's override to a row's resolved figure `resolved` ({ perKg, researched, comment, note, sources }). A price-only override keeps using whatever
// weight was already resolved (recovered algebraically as price/perKg); a weight-only override keeps the source's own price.
export function applyCustomOverride(price, resolved, override) {
  if (!override || (override.custom_price == null && override.custom_weight_kg == null)) return resolved
  const effectivePrice = override.custom_price ?? price
  const priorWeightKg = resolved.perKg !== null && price ? price / resolved.perKg : null
  const effectiveWeightKg = override.custom_weight_kg ?? priorWeightKg
  if (!effectiveWeightKg) {
    return {
      ...resolved,
      perKg: null,
      custom: true,
      comment: 'Custom price entered, but no pack weight is known yet — add a custom weight too, or research the item weights first.',
    }
  }
  const parts = []
  if (override.custom_price != null) parts.push(`price $${override.custom_price}`)
  if (override.custom_weight_kg != null) parts.push(`weight ${override.custom_weight_kg} kg`)
  return {
    perKg: effectivePrice / effectiveWeightKg,
    researched: false,
    custom: true,
    comment: `Custom value entered by user (${parts.join(', ')}).`,
    note: null,
    sources: [],
  }
}
