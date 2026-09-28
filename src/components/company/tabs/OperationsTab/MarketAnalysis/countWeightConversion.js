// Count-based -> weight-based price conversion for Market Opportunities'
// cross-country product matching (src/services/marketOpportunities.js).
//
// unitConversion.js's resolveColombiaWeightKg and genericUnitConversion.js's
// resolveGenericWeightKg both deliberately return a null weight for a count
// unit (Colombia's "unidad"/"docena"/"N per package"; a custom source's
// "each"/"unit"/"100's"/a bare "Bag"/"Bundle"/"Head") — correct, since
// neither module has a safe universal item weight to fall back on, and an
// invented one would silently corrupt every downstream $/kg figure. That
// null is the end of the line for those two modules BY DESIGN.
//
// This module is the deliberate next step, for exactly the case Market
// Opportunities actually needs it: a matched cross-country product pair
// where ONE side is that still-null count-based price and the OTHER side
// already has a real weight-based $/kg figure — e.g. Colombia sells eggs
// "por unidad" (per egg) while a target market prices them per kg. Two
// tiers, in order:
//
//   1. Eggs — deterministic, zero cost. USDA AMS's own official minimum
//      net-weight-per-dozen standard (unitConversion.js's EGG_DOZEN_OZ,
//      reused verbatim here, never redeclared) converts a price-per-egg to
//      a price-per-kg: price-per-egg -> price-per-dozen -> divide by the
//      dozen's official standard weight. Colombia's own grading scales
//      (La Mayorista's A/AA/AAA; Corabastos' A/AA/B/Extra) have NO
//      established correspondence to USDA's Jumbo/Extra Large/Large/
//      Medium/Small/Peewee size classes — confirmed by checking
//      productTranslations.js's own huevo-* entries and the rest of this
//      app for any such mapping; none exists, because none is real. Every
//      Colombia (or other non-USDA-graded) egg therefore maps to USDA
//      "Large" as an explicit, disclosed default (`assumedGradeDefault:
//      true` on the result) — the dozen-weight figure itself is still a
//      real USDA standard, but WHICH size class applies to this specific
//      grade is a guess, and the two are never allowed to look equally
//      certain on the resulting comparison row.
//
//   2. Everything else (e.g. Trinidad's "papaya, box of 18" style
//      packaging) — a single Haiku (claude-haiku-4-5, no web search, no
//      tools) estimate of the typical total net weight of the exact
//      priced pack, cached forever per distinct product name
//      (backend/unit_weight_estimates/ — its own new table, NOT
//      ProductWeightResearch/weight_research.py's Sonnet+web-search
//      pipeline, which is a different, more expensive mechanism already
//      wired up for a different purpose — see that module's own header for
//      why reusing it here would defeat the point). Paid at most once per
//      distinct product for the whole app, never per comparison/run.
//
// Both tiers only ever activate for a product whose OWN unit conversion
// already came back null AND whose raw unit is recognizably COUNT-based
// (not "no unit stated at all", not a volume unit like liters/cm3 — those
// stay unconvertible exactly as before, unrelated problems this module
// doesn't touch).

import { EGG_DOZEN_OZ, OZ_TO_KG } from './unitConversion'

// ------------------------------------------------------------ classification

// Colombia (La Mayorista/Corabastos): `unit === 'other'` with a unitLabel
// resolveColombiaWeightKg already gave up on (no libra/arroba/kilos/gramos/
// libras match) is count-based when it's the bare "unidad"/"docena" word, a
// leading "<N> UNIDADES" count (Corabastos' own "30 UNIDADES (1 per
// package)" phrasing), or this source's general "<PACKAGING> (<N> per
// package)" shape (verified live against every real unitLabel this app's
// own Colombia snapshots currently hold before writing these patterns, not
// guessed).
//
// Whether `price` covers the WHOLE priced batch (itemCount items) or is
// ALREADY per one single item depends on which of these shapes matched —
// this isn't a stylistic choice, it comes straight from corabastos.py's own
// documented rule ("Precio Unidad is always Precio Extra / Cantidad"),
// confirmed against a real pair of rows:
//   - "30 UNIDADES (1 per package)" (eggs): the item count (30) is the
//     PRESENTACION prefix; Cantidad itself is 1 (one package), so Precio
//     Unidad = Precio Extra / 1 is unchanged — `price` is for the WHOLE
//     30-item package. perSingleItem: false (divide by itemCount to reach
//     a per-item price, same as before).
//   - "CAJA DE MADERA (18 per package)" (papaya): here Cantidad IS the 18 —
//     Corabastos already computed Precio Unidad = Precio Extra / 18 before
//     this app ever sees it, so `price` is ALREADY per one single item.
//     perSingleItem: true — dividing it by itemCount again would silently
//     shrink it ~18x (confirmed live: this was producing $0.05/kg for
//     papaya priced at COP 1,556/unit against a ~3,334 COP/USD rate, when
//     the correct figure is ~$0.93/kg).
const UNIDADES_PREFIX_RE = /^(\d+)\s*unidades\b/i
const PER_PACKAGE_RE = /\((\d+)\s*per package\)/i

export function classifyColombiaCountUnit(unit, unitLabel) {
  if (unit !== 'other' || !unitLabel) return null
  const trimmed = unitLabel.trim()
  const lower = trimmed.toLowerCase()
  if (lower === 'unidad') return { itemCount: 1, packDescription: '1 unit ("unidad")', perSingleItem: false }
  if (lower === 'docena') return { itemCount: 12, packDescription: 'a dozen ("docena")', perSingleItem: false }
  const unidadesMatch = trimmed.match(UNIDADES_PREFIX_RE)
  if (unidadesMatch) return { itemCount: parseInt(unidadesMatch[1], 10), packDescription: trimmed, perSingleItem: false }
  const perPackageMatch = trimmed.match(PER_PACKAGE_RE)
  if (perPackageMatch) return { itemCount: parseInt(perPackageMatch[1], 10), packDescription: trimmed, perSingleItem: true }
  return null
}

// Custom sources (Jamaica/Saint Lucia/Trinidad and Tobago today, via
// genericUnitConversion.js): 'each'/'unit' (one item), a "<N>'s" count
// (Trinidad's "100's" produce-count convention), or a bare packaging word
// with no stated count or weight at all ("Bag", "Bndl.", "Bundle", "Head")
// — still count-based, just without a parseable item count. That's fine:
// the generic (non-egg) Haiku tier below asks for the whole pack's weight
// directly, the same way usaWeightResearchItem/colombiaWeightResearchItem
// already do for their own unconvertible cases — only the egg formula
// actually needs a per-item count.
const HUNDREDS_RE = /^(\d+)\s*['’]?s$/i
const BARE_PACK_WORDS = new Set(['bag', 'bndl.', 'bndl', 'bundle', 'head'])

export function classifyGenericCountUnit(unit) {
  if (!unit || !unit.trim()) return null
  const trimmed = unit.trim()
  const lower = trimmed.toLowerCase()
  if (lower === 'each' || lower === 'unit') return { itemCount: 1, packDescription: `1 ${lower}` }
  const hundredsMatch = trimmed.match(HUNDREDS_RE)
  if (hundredsMatch) return { itemCount: parseInt(hundredsMatch[1], 10), packDescription: trimmed }
  if (BARE_PACK_WORDS.has(lower)) return { itemCount: null, packDescription: trimmed }
  return null
}

// ------------------------------------------------------------------- eggs

// Real HS code for birds' eggs in shell (Chapter 4, heading 0407) — used
// (when the classification cache already has it) as a language-independent
// "is this actually an egg product" signal alongside a plain name check, so
// this doesn't depend on Colombia's Spanish being translated first.
export function isEggProduct(hsCode, displayName) {
  if (hsCode && hsCode.startsWith('0407')) return true
  return /\begg|\bhuevo/i.test(displayName || '')
}

// Formula (deterministic, no network call): price-per-egg -> price-per-
// dozen -> divide by USDA's official standard dozen weight for the given
// size class. `itemCount` is how many individual eggs the priced unit
// actually covers (1 for "unidad", 30 for "30 UNIDADES (1 per package)",
// etc). Every non-USDA-graded egg (Colombia today) is looked up under
// "Large" — see this module's own header for why that's an explicit,
// disclosed default rather than a real known grade.
const DEFAULT_EGG_SIZE = 'Large'

export function resolveEggPriceViaUsdaStandard(price, itemCount, perSingleItem = false) {
  if (price == null || !itemCount || itemCount <= 0) return null
  const sizeEntry = EGG_DOZEN_OZ.find(([size]) => size === DEFAULT_EGG_SIZE)
  if (!sizeEntry) return null
  const [size, oz] = sizeEntry
  const dozenWeightKg = oz * OZ_TO_KG
  // See classifyColombiaCountUnit's own header: some count shapes (Corabastos'
  // "(N per package)") already report a per-single-egg price — dividing by
  // itemCount again would silently shrink it ~N-fold.
  const pricePerEgg = perSingleItem ? price : price / itemCount
  const perKg = (pricePerEgg * 12) / dozenWeightKg
  return {
    perKg,
    method: 'usda_standard',
    assumedGradeDefault: true,
    conversionNote:
      `Converted via USDA AMS's official minimum net weight standard for "${size}" eggs ` +
      `(${oz} oz/dozen = ${dozenWeightKg.toFixed(3)} kg/dozen), applied as price-per-egg → price-per-dozen → ` +
      `price-per-kg (${
        perSingleItem
          ? `this source already prices a single egg out of its ${itemCount}-egg pack`
          : `${itemCount} egg${itemCount === 1 ? '' : 's'} per priced unit`
      }). This source's own grading ` +
      `scale has no established correspondence to USDA's Jumbo/Extra Large/Large/Medium/Small/Peewee size ` +
      `classes, so "${size}" was used as an explicit default, not a confirmed match to this grade.`,
  }
}

// ------------------------------------------------------- everything else

// Cache key: the product's own display name, trimmed/lowercased — the SAME
// convention computeMarketOpportunity() already uses for the HS-code cache
// (hsByExactName), deliberately NOT productTranslations.js's
// normalizeProductName (which strips parentheticals) — "Pimento (S)" and
// "Pimento (S)(20lb)" are genuinely different pack sizes with genuinely
// different real weights, and collapsing them into one signature would
// silently apply the wrong pack's estimate to the other.
export function genericWeightSignature(displayName) {
  return displayName.trim().toLowerCase()
}

export function buildGenericWeightDescription(displayName, packDescription, perSingleItem = false) {
  if (perSingleItem) {
    return (
      `"${displayName}" is sold as "${packDescription}", but the price is already quoted per SINGLE item, ` +
      `not per whole pack (see classifyColombiaCountUnit). What is the typical net weight, in grams, of just ONE such single item?`
    )
  }
  return `"${displayName}", sold as "${packDescription}". What is the typical TOTAL net weight, in grams, of ONE such priced unit/pack?`
}

export function resolveGenericPriceFromWeightGrams(price, weightGrams) {
  if (price == null || !weightGrams || weightGrams <= 0) return null
  const weightKg = weightGrams / 1000
  return price / weightKg
}
