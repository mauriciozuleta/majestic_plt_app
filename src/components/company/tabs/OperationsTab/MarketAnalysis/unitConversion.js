// Standardized $/kg conversion for the product tables. Computed ONLY where
// the source data states (or implies via a fixed, official unit-weight
// standard) a real, unambiguous mass — never a guessed average per-item
// weight. A wrong constant here would quietly corrupt every downstream
// price comparison and competitive-analysis figure, which is worse than
// just not offering a number, so an unconvertible row returns null rather
// than an invented estimate.
//
// Every conversion path also carries a plain-language "comment" explaining
// how the number was produced (official / AI-researched / custom, or why
// it couldn't be computed at all) — shown in the table's Comments column
// so the user can judge each figure rather than take it on faith.

const LB_TO_KG = 0.45359237
const OZ_TO_KG = 0.028349523125
const CWT_TO_KG = 100 * LB_TO_KG
const ARROBA_TO_KG = 25 * LB_TO_KG // Colombian arroba — a fixed traditional unit, always 25 lb

// USDA's official minimum net weight per dozen, by egg size class (oz per
// dozen) — a fixed regulatory grading standard, not an estimate. Checked in
// this order so "Extra Large" matches before the plain "Large" substring.
const EGG_DOZEN_OZ = [
  ['Jumbo', 30],
  ['Extra Large', 27],
  ['Large', 24],
  ['Medium', 21],
  ['Small', 18],
  ['Peewee', 15],
]

// USDA standard test weight per bushel, by grain (lb per bushel) — fixed by
// federal grain-standards regulation, not an estimate.
const BUSHEL_LB = [
  ['Corn', 56],
  ['Soybeans', 60],
  ['Wheat', 60],
]

// Colombia (La Mayorista / Corabastos). `unit === 'kg'` means the source's
// own price is already per kilogram — no conversion needed. `unit ===
// 'other'` needs `unitLabel` parsed for an exact stated weight: "libra"
// (pound), "arroba" (25 lb), or a package that states its own weight
// directly ("bulto de 50 kilos", "400 gramos"). Count units (unidad,
// docena) and volume units (cm3, ml — a different physical quantity
// entirely) have no safe conversion and deliberately return a null weight.
function resolveColombiaWeightKg(unit, unitLabel) {
  if (unit === 'kg') return { weightKg: 1, comment: 'Source already reports a price per kilogram — no conversion needed.' }
  if (!unitLabel) {
    return { weightKg: null, comment: 'No unit label reported by the source — cannot determine a weight.' }
  }
  const lower = unitLabel.toLowerCase()
  if (lower === 'libra') {
    return { weightKg: LB_TO_KG, comment: `Converted from "libra" (1 libra = ${LB_TO_KG.toFixed(4)} kg).` }
  }
  if (lower === 'arroba') {
    return {
      weightKg: ARROBA_TO_KG,
      comment: `Converted from "arroba" (1 arroba = 25 lb = ${ARROBA_TO_KG.toFixed(2)} kg, a fixed Colombian traditional unit).`,
    }
  }
  const kilosMatch = lower.match(/(\d+(?:\.\d+)?)\s*kilos?\b/)
  if (kilosMatch) {
    const kg = parseFloat(kilosMatch[1])
    return { weightKg: kg, comment: `Converted using the package's own stated weight ("${unitLabel}" = ${kg} kg).` }
  }
  const gramosMatch = lower.match(/(\d+(?:\.\d+)?)\s*gramos?\b/)
  if (gramosMatch) {
    const kg = parseFloat(gramosMatch[1]) / 1000
    return { weightKg: kg, comment: `Converted using the package's own stated weight ("${unitLabel}" = ${kg} kg).` }
  }
  const librasMatch = lower.match(/(\d+(?:\.\d+)?)\s*libras?\b/)
  if (librasMatch) {
    const lbs = parseFloat(librasMatch[1])
    const kg = lbs * LB_TO_KG
    return { weightKg: kg, comment: `Converted using the package's own stated weight ("${unitLabel}" = ${lbs} lb = ${kg.toFixed(2)} kg).` }
  }
  return {
    weightKg: null,
    comment: `"${unitLabel}" is a count or volume unit with no weight stated by the source — cannot convert to $/kg without knowing the package's real weight.`,
  }
}

export function colombiaPricePerKg(price, unit, unitLabel) {
  if (price === null || price === undefined) return null
  const { weightKg } = resolveColombiaWeightKg(unit, unitLabel)
  return weightKg !== null ? price / weightKg : null
}

export function explainColombiaConversion(unit, unitLabel) {
  return resolveColombiaWeightKg(unit, unitLabel).comment
}

// USA (USDA AMS reports). Beef/Pork (cwt), Poultry (lb), Eggs (dozen, by
// graded size), and Grains (bushel, by grain) all convert via a fixed,
// official unit definition. Produce (CA/FL shipping-point reports) is
// priced per carton/pack, and this app's scraper does not capture that
// pack's actual net weight from the source PDF's "Basis" line (a real
// figure exists there, e.g. "19 lb containers bagged", but reliably
// attributing it per price row across that report's layout isn't done yet)
// — so no per-kg figure is offered for Produce rather than assuming a
// carton weight.
function resolveUsaWeightKg(product) {
  const { unit, product_en: productEn } = product
  if (unit === 'USD/cwt (100lb)') {
    return { weightKg: CWT_TO_KG, comment: `Official: 1 cwt = 100 lb = ${CWT_TO_KG.toFixed(3)} kg.` }
  }
  if (unit === 'USD/lb') {
    return { weightKg: LB_TO_KG, comment: `Official: 1 lb = ${LB_TO_KG.toFixed(4)} kg.` }
  }
  if (unit && unit.startsWith('USD/dozen')) {
    const sizeEntry = EGG_DOZEN_OZ.find(([size]) => productEn.includes(size))
    if (!sizeEntry) return { weightKg: null, comment: 'Egg size grade not recognized in the product name — cannot look up its official dozen weight.' }
    const [size, oz] = sizeEntry
    const kg = oz * OZ_TO_KG
    return { weightKg: kg, comment: `Official USDA minimum net weight for "${size}" eggs: ${oz} oz/dozen = ${kg.toFixed(3)} kg.` }
  }
  if (unit === 'USD/bushel') {
    const grainEntry = BUSHEL_LB.find(([grain]) => productEn.includes(grain))
    if (!grainEntry) return { weightKg: null, comment: 'Grain type not recognized in the product name — cannot look up its official bushel weight.' }
    const [grain, lb] = grainEntry
    const kg = lb * LB_TO_KG
    return { weightKg: kg, comment: `Official USDA standard test weight for ${grain}: ${lb} lb/bushel = ${kg.toFixed(3)} kg.` }
  }
  return {
    weightKg: null,
    comment:
      'Priced per carton/pack — this report does not state the carton\'s net weight, so no official $/kg conversion is available. ' +
      'Use "Research Missing Weights", or enter a custom weight.',
  }
}

export function usaPricePerKg(product) {
  const { price } = product
  if (price === null || price === undefined) return null
  const { weightKg } = resolveUsaWeightKg(product)
  return weightKg !== null ? price / weightKg : null
}

export function explainUsaConversion(product) {
  return resolveUsaWeightKg(product).comment
}

// --- AI weight research (see src/services/weightResearch.js) ---
//
// For the one USA category group that stays unconvertible above (Produce)
// and for Colombia's count-based packages, a stable "signature" identifies
// the PACK itself — not the priced row — so every size/count grade of the
// same carton (32s, 36s, 48s, ...) shares one signature and gets researched
// once, since the carton's real weight doesn't depend on which size grade
// is inside it.

export function usaWeightResearchItem(product) {
  if (!product.category.startsWith('Produce')) return null // everything else already has a fixed official conversion
  const signature = `usa:${product.category}:${product.product_en}`
  const sizeLabel = (product.unit || '').replace(/^USD\/carton or pack — /, '')
  const description =
    `USDA AMS wholesale/shipping-point market news report — "${product.product_en}" (category: ${product.category}), ` +
    `sold in cartons/packs graded by size (e.g. "${sizeLabel}"). What is the standard/typical net weight in ` +
    'kilograms of ONE such wholesale carton — the carton format itself is the same across size grades, only the ' +
    'produce count or size varies?'
  return { signature, description }
}

export function colombiaWeightResearchItem(category, productName, unitLabel, sourceLabel) {
  const signature = `colombia:${category}:${productName.toLowerCase()}:${unitLabel}`
  const description =
    `Colombian wholesale market (${sourceLabel}) — "${productName}" sold as "${unitLabel}". What is the ` +
    'standard/typical net weight in kilograms of ONE such package?'
  return { signature, description }
}

// --- Custom-override row signatures (see src/services/productOverrides.js) ---
//
// Finer-grained than the weight-research signatures above: a price
// correction is naturally per exact priced row (a specific product at a
// specific source, or a specific size grade), not shared across every
// size/source variant of the same product.

export function colombiaRowSignature(category, productName, sourceLabel) {
  return `colombia-row:${category}:${productName.toLowerCase()}:${sourceLabel}`
}

export function usaRowSignature(product) {
  return `usa-row:${product.category}:${product.product_en}:${product.unit}`
}

// Resolves a row's effective $/kg: the official conversion when it exists
// (comment = officialComment, passed in from explainColombiaConversion/
// explainUsaConversion), otherwise a researched fallback (never the
// reverse — a researched estimate never overrides a real, fixed
// conversion). `researchedWeights` is a Map<signature, {weight_kg,
// confidence, note, sources}> from the weight-research API.
export function applyResearchedWeight(price, basePerKg, officialComment, signature, researchedWeights) {
  if (basePerKg !== null) return { perKg: basePerKg, researched: false, comment: officialComment, note: null, sources: [] }
  const research = signature ? researchedWeights.get(signature) : null
  if (!research || research.weight_kg === null || research.weight_kg === undefined) {
    const comment = research?.note ? `AI research found no reliable weight: ${research.note}` : officialComment
    return { perKg: null, researched: false, comment, note: research?.note ?? null, sources: [] }
  }
  return {
    perKg: price / research.weight_kg,
    researched: true,
    comment: `AI-researched pack weight (${research.confidence || 'unknown'} confidence): ${research.note || 'no note provided'}`,
    note: research.note || null,
    sources: research.sources || [],
  }
}

// --- Custom user overrides (see src/services/productOverrides.js) ---
//
// The manual escape hatch: a user-entered price and/or pack weight for one
// exact row, always taking priority over both the official conversion and
// any AI research. A price-only override keeps using whatever weight was
// already resolved (recovered algebraically as price/perKg, since the
// resolve functions above don't separately expose the weight they used);
// a weight-only override keeps the source's own price.
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
      comment: 'Custom price entered, but no pack weight is known yet — add a custom weight too, or run "Research Missing Weights" first.',
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
