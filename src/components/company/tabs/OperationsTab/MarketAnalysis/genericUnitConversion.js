// Deterministic kg/g/lb/oz(/L/gal) unit conversion for CUSTOM product-
// analysis sources (Jamaica, Saint Lucia, Trinidad and Tobago today) — the
// same discipline as unitConversion.js's Colombia/USA resolvers (official,
// fixed factors only; an unconvertible row returns null with a plain-
// language comment, never a guessed number), generalized to whatever unit
// text a custom source actually states, since those sources aren't the
// fixed Colombia/USA shapes that file's own regexes are written for.
//
// Verified against every real row currently loaded from all three live
// custom sources (`GET /product-sources/products`) before writing this,
// not guessed: Jamaica (moa.gov.jm) and Saint Lucia (Massy Stores) already
// report a clean 'kg' / 'g' / 'each' / 'unit' value. Trinidad's namdevco
// source is the one with the same "the real weight is embedded in
// unstructured unit text" problem Colombia's own parser already solved for
// "bulto de 50 kilos" — just in English and with different package words
// ("45kg bag", "100lb bag", "22.68kg bag", "5lb bundle", "40lb box") — so
// the regex below is that exact approach, reused, not re-derived.

const LB_TO_KG = 0.45359237
const OZ_TO_KG = 0.028349523125
const G_TO_KG = 0.001

const VOLUME_UNITS = new Set(['l', 'liter', 'liters', 'litre', 'litres', 'ml', 'milliliter', 'milliliters', 'gal', 'gallon', 'gallons'])

// A bare weight-unit word (singular or plural) -> its factor in kg. Also
// used to resolve the unit word captured out of a package-weight phrase
// like "45kg bag" below.
function weightUnitToKgFactor(word) {
  const singular = word.toLowerCase().replace(/s$/, '')
  if (singular === 'kg' || singular === 'kilogram') return 1
  if (singular === 'g' || singular === 'gram') return G_TO_KG
  if (singular === 'lb' || singular === 'pound') return LB_TO_KG
  if (singular === 'oz' || singular === 'ounce') return OZ_TO_KG
  return null
}

// Matches a number immediately followed by a weight-unit word anywhere in
// the unit text — "45kg bag", "100lb bag", "22.68kg bag", "5lb bundle",
// "40lb box" all match; the surrounding "bag"/"box"/"bundle" word is
// ignored (it's packaging language, not part of the weight itself).
const PACKAGE_WEIGHT_RE = /(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams?|lbs?|pounds?|oz|ounces?)\b/i

// `productName` matters for a bare weight unit: a retail source (Saint
// Lucia's Massy Stores) reports unit "g" or "kg" for a fixed pack whose net
// weight is in the name — "Picsweet Green Peas 340G" at XCD 12.15 is the
// price of one 340 g pack, not of one gram, and "Imported Apple Red Bag
// Prepacked 1.4KG" is the price of the 1.4 kg bag. A pack weight stated in
// the name therefore wins over the bare unit.
export function resolveGenericWeightKg(unit, productName = '') {
  if (!unit || !unit.trim()) {
    return { weightKg: null, comment: 'No unit reported by the source — cannot determine a weight.' }
  }
  const trimmed = unit.trim()
  const lower = trimmed.toLowerCase()

  const bareFactor = weightUnitToKgFactor(lower)
  const namePackMatch = bareFactor !== null ? (productName || '').match(PACKAGE_WEIGHT_RE) : null
  if (namePackMatch) {
    const amount = parseFloat(namePackMatch[1])
    const perUnitKg = weightUnitToKgFactor(namePackMatch[2])
    if (perUnitKg !== null && amount > 0) {
      const kg = amount * perUnitKg
      return {
        weightKg: kg,
        comment: `Priced per pack — the product name states its net weight ("${namePackMatch[0]}" = ${kg.toFixed(3)} kg).`,
      }
    }
  }
  if (bareFactor !== null) {
    return {
      weightKg: bareFactor,
      comment: `Source already reports a price per "${trimmed}" — official conversion (1 ${lower.replace(/s$/, '')} = ${bareFactor.toFixed(6)} kg).`,
    }
  }

  if (VOLUME_UNITS.has(lower)) {
    return {
      weightKg: null,
      comment: `"${trimmed}" is a volume unit — a different physical quantity from weight — no safe $/kg conversion is possible without a product-specific density.`,
    }
  }

  const packageMatch = trimmed.match(PACKAGE_WEIGHT_RE)
  if (packageMatch) {
    const amount = parseFloat(packageMatch[1])
    const perUnitKg = weightUnitToKgFactor(packageMatch[2])
    if (perUnitKg !== null && amount > 0) {
      const kg = amount * perUnitKg
      return { weightKg: kg, comment: `Converted using the package's own stated weight ("${trimmed}" = ${kg.toFixed(3)} kg).` }
    }
  }

  return {
    weightKg: null,
    comment: `"${trimmed}" is a count or package unit with no weight stated by the source — needs an AI-researched pack weight (see "Research Missing Weights") or a custom override before it can convert to $/kg.`,
  }
}

export function genericPricePerKg(price, unit, productName = '') {
  if (price === null || price === undefined) return null
  const { weightKg } = resolveGenericWeightKg(unit, productName)
  return weightKg !== null ? price / weightKg : null
}

export function explainGenericConversion(unit, productName = '') {
  return resolveGenericWeightKg(unit, productName).comment
}

// Same AI-weight-research fallback item shape as
// usaWeightResearchItem/colombiaWeightResearchItem (unitConversion.js) —
// reused, not reimplemented — for a custom source's own unresolved unit.
// The signature is per (country, source, product, unit) since, unlike
// Colombia's shared package sizes, a custom source's own package wording
// is specific to that one source.
export function genericWeightResearchItem(countryName, sourceName, productName, unit) {
  const signature = `generic:${countryName}:${sourceName}:${productName.toLowerCase()}:${unit}`
  const description =
    `${sourceName} (${countryName}) — "${productName}" sold as "${unit}". What is the standard/typical net weight ` +
    'in kilograms of ONE such unit/package?'
  return { signature, description }
}
