// Local static Spanish -> English dictionary for wholesale produce/food
// names, per spec §6 — no AI/runtime translation, since an incorrect
// product-name translation in a sourcing tool could cause a real mismatched
// purchase. Keyed by a normalized form of the name (lowercase, accents
// stripped, trailing parenthetical unit notes like "(kilo)" removed) so
// La Mayorista's and Corabastos' differently-capitalized/annotated spellings
// of the same product both resolve to one entry.
//
// Source of truth: spanish-english-product-reference.md (the canonical
// name-translation reference built from both sources' real catalogs).
// Where that document says "no direct US equivalent," the native term is
// kept with a description rather than an invented English name. Several
// entries carry a deliberate disambiguation — e.g. Ají (chili pepper) vs.
// Pimentón (bell pepper), or Habichuela (pod bean) vs. Frijol Verde (shelled
// bean) — so the app never conflates two genuinely different products.
//
// Coverage: every product name in the reference document, plus a handful of
// real raw-name variants observed in actual bulletins that the document
// doesn't spell out verbatim (unit-suffixed forms like "x tonelada", grade
// suffixes, etc.) — noted inline where added for that reason. Anything else
// falls back to the Spanish name with a visible "translation needed" marker
// (see translateProductName below) rather than guessing.

import PRODUCT_TRANSLATIONS_JSON from '../../../../../../backend/catalog_normalization/data/product_translations_es_en.json'

function stripAccents(value) {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '')
}

export function normalizeProductName(nameEs) {
  return stripAccents(nameEs.toLowerCase())
    .replace(/\([^)]*\)/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Tier 2 of the translation fallback chain (see backend/translation/resolve.py
// for tiers 3-4): a name that misses the dictionary outright is often just a
// typo/variant/grade-suffix of a name the dictionary already has (e.g.
// "Tomate Chonto Extra" vs. "Tomate Chonto") — a plain Levenshtein similarity
// ratio against every known key (the static dictionary plus confirmed
// overrides) catches most of those for free, no model or network call
// needed. Above FUZZY_MATCH_THRESHOLD a match is used directly, same as an
// exact hit; below it, the caller falls through to asking for an AI
// suggestion (tiers 3-4) instead.
const FUZZY_MATCH_THRESHOLD = 0.85

function levenshteinDistance(a, b) {
  const rows = a.length + 1
  const cols = b.length + 1
  const dp = Array.from({ length: rows }, () => new Array(cols).fill(0))
  for (let i = 0; i < rows; i += 1) dp[i][0] = i
  for (let j = 0; j < cols; j += 1) dp[0][j] = j
  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      dp[i][j] =
        a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] : 1 + Math.min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])
    }
  }
  return dp[rows - 1][cols - 1]
}

function similarityRatio(a, b) {
  const maxLen = Math.max(a.length, b.length)
  if (maxLen === 0) return 1
  return 1 - levenshteinDistance(a, b) / maxLen
}

// Best dictionary/override key fuzzy-matching `key`, or null if nothing
// clears FUZZY_MATCH_THRESHOLD.
function findFuzzyKey(key, knownKeys) {
  let bestKey = null
  let bestRatio = FUZZY_MATCH_THRESHOLD
  for (const candidateKey of knownKeys) {
    const ratio = similarityRatio(key, candidateKey)
    if (ratio >= bestRatio) {
      bestRatio = ratio
      bestKey = candidateKey
    }
  }
  return bestKey
}

// The dictionary itself lives in the backend's catalog normalization module (one shared file, so the module, the price comparison and every table read
// the same translations): backend/catalog_normalization/data/product_translations_es_en.json, keyed by normalizeProductName(). Edit it there.
export const PRODUCT_TRANSLATIONS = PRODUCT_TRANSLATIONS_JSON

/** Returns { text, isTranslated } — falls back to the Spanish name with
 * isTranslated:false rather than guessing, per spec §6. */
// `overrides` are user-submitted translations fetched from the backend
// (see priceComparisonFetchers.fetchTranslationOverrides) for products the
// static dictionary above doesn't cover yet — keyed the same way, so they
// slot into the same lookup. An override wins over the static dictionary,
// letting a user correct a wrong static entry too.
export function translateProductName(nameEs, overrides = {}) {
  const key = normalizeProductName(nameEs)
  const direct = overrides[key] || PRODUCT_TRANSLATIONS[key]
  if (direct) return { text: direct, isTranslated: true }

  const fuzzyKey = findFuzzyKey(key, Object.keys(PRODUCT_TRANSLATIONS).concat(Object.keys(overrides)))
  if (fuzzyKey) {
    const fuzzyTranslation = overrides[fuzzyKey] || PRODUCT_TRANSLATIONS[fuzzyKey]
    return { text: fuzzyTranslation, isTranslated: true }
  }

  return { text: nameEs, isTranslated: false }
}
