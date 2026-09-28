// Market Opportunities' real engine: cross-country wholesale price
// comparison + opportunity scoring, replacing MarketOpportunitiesPanel.jsx's
// original "coming soon" placeholder. Product matching (curated overrides +
// translated/exact normalized-name join + a shared-HS-code fallback) and
// unit/currency normalization happen HERE, on the frontend — composing
// pieces this app already built for exactly this rather than inventing a
// new mechanism:
//   - priceComparisonData.js's mergeSources() shape (full outer join,
//     unmatched never dropped) and productTranslations.js's
//     translateProductName()/normalizeProductName() for Colombia, both
//     frontend-only by design (Colombia's raw names are Spanish).
//   - unitConversion.js's colombiaPricePerKg/usaPricePerKg (official,
//     fixed-factor conversion, an unconvertible row returns null) for the
//     two built-in country pipelines, and this feature's own
//     genericUnitConversion.js (same discipline, generalized to custom
//     sources) for every other country.
//   - crossCountryMatchOverrides.js — match_table.py's own curated-dict
//     pattern, generalized to arbitrary country pairs.
//   - productHsCodes.js's own classification cache (the same one
//     buildProductPortfolio()/buildCategoryCoverage() already read) as a
//     THIRD, lower-confidence matching tier: two products with completely
//     different display names (e.g. Colombia's "chonto tomato" and
//     Jamaica's "tomato [plummy] (local)") but the same already-classified
//     HS code are still the same real product type, and an exact-name-only
//     join was silently excluding every one of them — confirmed live
//     against this app's own real data before building this (many Colombia
//     and Jamaica tomato variants all classify to HS 070200 under
//     completely different names). Never a NEW classification mechanism —
//     this only reads the cache the existing background pipeline already
//     populates; a product not yet classified simply isn't eligible for
//     this tier yet, same as everywhere else in this app that reads it.
// The backend (routers/market_opportunities.py) only ever does two things:
// a free/keyless FX rate with its own date, every currency converting
// independently to a common USD basis (open.er-api.com, see
// backend/currency/usd_rates.py), and persisting + scoring (the
// opportunity-rating scale) the final rows this module builds.

import { API_BASE } from './apiBase'
import { fetchReferenceCountries } from './commercialStructure'
import { fetchCustomSourceProducts } from './productSources'
import { mergeSources } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData'
import { translateProductName, normalizeProductName } from '../components/company/tabs/OperationsTab/MarketAnalysis/productTranslations'
import {
  fetchPriceComparisonSnapshot,
  fetchTranslationOverrides,
} from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'
import { colombiaPricePerKg, explainColombiaConversion, usaPricePerKg, explainUsaConversion } from '../components/company/tabs/OperationsTab/MarketAnalysis/unitConversion'
import { genericPricePerKg, explainGenericConversion } from '../components/company/tabs/OperationsTab/MarketAnalysis/genericUnitConversion'
import {
  classifyColombiaCountUnit,
  classifyGenericCountUnit,
  isEggProduct,
  resolveEggPriceViaUsdaStandard,
  genericWeightSignature,
  buildGenericWeightDescription,
  resolveGenericPriceFromWeightGrams,
} from '../components/company/tabs/OperationsTab/MarketAnalysis/countWeightConversion'
import { lookupCrossCountryOverride } from '../data/crossCountryMatchOverrides'
import { fetchProductHsCodes } from './productHsCodes'
import { requestUnitWeightEstimates } from './unitWeightEstimates'

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

// { rate, date, from, available } — every currency converts independently
// to a common USD basis (never source-currency straight to target-currency
// — see buildComparisonRow below), via open.er-api.com (backend/currency/
// usd_rates.py), which — unlike this feature's original Frankfurter/ECB
// source — actually covers COP/JMD/XCD/TTD, this app's own real
// tracked-country currencies (confirmed live). `rate` is how many units of
// `fromCurrency` equal 1 USD — DIVIDE a local price by it to get USD, never
// multiply (see usd_rates.py's own docstring for why this direction is
// deliberate). `available: false` only if the currency truly has no rate
// anywhere (not a real 3-letter code, or genuinely unsupported) — never
// thrown as an error, the caller shows the affected side as unresolved,
// same as an unconvertible unit.
export async function fetchMarketOpportunityExchangeRate(fromCurrency) {
  const params = new URLSearchParams({ from: fromCurrency })
  return fetchJson(`/api/market-opportunities/exchange-rate?${params.toString()}`)
}

export async function saveMarketOpportunityComparisons(rows) {
  return fetchJson('/api/market-opportunities/comparisons', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  })
}

export async function fetchMarketOpportunityComparisons(sourceCountry, targetCountries) {
  const params = new URLSearchParams({ source_country: sourceCountry, target_countries: targetCountries.join(',') })
  return fetchJson(`/api/market-opportunities/comparisons?${params.toString()}`)
}

// ---------------------------------------------------------------- collectors
//
// Every collector returns the same shape regardless of country, so the
// matching/scoring code below never needs to know which pipeline a product
// came from:
//   { matchName, displayName, category, sourceLabel, priceValue, priceUnit,
//     priceCurrency, perKgLocal, unitComment, translated }
// `perKgLocal` is the price per kilogram in the product's OWN currency
// (null if its unit couldn't be converted — the discipline every existing
// conversion path in this app already follows); `translated` is only ever
// true for a Colombia product whose Spanish name resolved through
// productTranslations.js.

async function collectColombiaComparisonProducts() {
  const [snapshots, overrides] = await Promise.all([
    fetchPriceComparisonSnapshot(),
    fetchTranslationOverrides().catch(() => []),
  ])
  const overridesByKey = Object.fromEntries(overrides.map((row) => [row.product_key, row.translation_en]))
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  if (!bySource.la_mayorista && !bySource.corabastos) return []
  const merged = mergeSources(bySource.la_mayorista || [], bySource.corabastos || [])

  return merged
    .filter((p) => p.laMayorista != null || p.corabastos != null)
    .map((p) => {
      const { text, isTranslated } = translateProductName(p.nameEs, overridesByKey)
      // Colombia has two independent wholesalers; a cross-country
      // comparison needs ONE real recorded price per product, never an
      // average blended into a fake "original" figure — La Mayorista's own
      // row is preferred when both have this product (arbitrary but
      // disclosed via sourceLabel, not hidden), otherwise whichever exists.
      const useLaMayorista = p.laMayorista != null
      const value = useLaMayorista ? p.laMayorista : p.corabastos
      const unit = useLaMayorista ? p.laMayoristaUnit : p.corabastosUnit
      const unitLabel = useLaMayorista ? p.laMayoristaUnitLabel : p.corabastosUnitLabel
      return {
        matchName: normalizeProductName(text),
        displayName: text,
        category: p.category,
        sourceLabel: useLaMayorista ? 'La Mayorista' : 'Corabastos',
        priceValue: value,
        priceUnit: unit === 'kg' ? 'kg' : unitLabel || unit,
        priceCurrency: 'COP',
        perKgLocal: colombiaPricePerKg(value, unit, unitLabel),
        unitComment: explainColombiaConversion(unit, unitLabel),
        translated: isTranslated,
        // Raw (untranslated-shape) unit fields — countWeightConversion.js's
        // classifyColombiaCountUnit needs the ORIGINAL unit/unitLabel pair
        // (e.g. unit === 'other', unitLabel === 'unidad'), not the merged
        // display string priceUnit already collapsed those into above.
        rawUnit: unit,
        rawUnitLabel: unitLabel,
      }
    })
}

async function collectUsaComparisonProducts() {
  const snapshots = await fetchUsaSourcingSnapshot()
  return snapshots.flatMap((s) =>
    s.products.map((p) => ({
      matchName: normalizeProductName(p.product_en),
      displayName: p.product_en,
      category: p.category,
      sourceLabel: s.source,
      priceValue: p.price,
      priceUnit: p.unit,
      priceCurrency: 'USD',
      perKgLocal: usaPricePerKg(p),
      unitComment: explainUsaConversion(p),
      translated: false,
    })),
  )
}

async function buildCountryCurrencyMap() {
  const rows = await fetchReferenceCountries().catch(() => [])
  return new Map(rows.map((row) => [row.name.trim().toLowerCase(), row.currency_code]))
}

const ISO_CURRENCY_RE = /^[A-Z]{3}$/

async function collectCustomComparisonProducts(countryName) {
  const [sources, currencyByCountry] = await Promise.all([fetchCustomSourceProducts(), buildCountryCurrencyMap()])
  const mine = sources.filter((row) => row.country_name.trim().toLowerCase() === countryName.trim().toLowerCase())
  // A product/source's own stated currency when it's a real ISO code;
  // otherwise the country's own official currency (already stored in this
  // app's reference catalog — a real, non-guessed fact, not an invented
  // one) — needed for real rows seen live where the source recorded no
  // currency at all (Trinidad and Tobago's namdevco feed) or a bare "$"
  // that isn't itself a valid ISO code (Saint Lucia's Massy Stores feed).
  const fallbackCurrency = currencyByCountry.get(countryName.trim().toLowerCase()) || null

  return mine.flatMap((source) =>
    source.products.map((product) => {
      const rawCurrency = (product.currency || source.currency || '').trim().toUpperCase()
      const currency = ISO_CURRENCY_RE.test(rawCurrency) ? rawCurrency : fallbackCurrency
      return {
        matchName: normalizeProductName(product.name),
        displayName: product.name,
        category: product.category,
        sourceLabel: source.source_name,
        priceValue: product.price,
        priceUnit: product.unit,
        priceCurrency: currency,
        perKgLocal: genericPricePerKg(product.price, product.unit),
        unitComment: explainGenericConversion(product.unit),
        translated: false,
        rawUnit: product.unit,
      }
    }),
  )
}

async function collectCountryComparisonProducts(countryName) {
  if (countryName === 'Colombia') return collectColombiaComparisonProducts()
  if (countryName === 'United States') return collectUsaComparisonProducts()
  return collectCustomComparisonProducts(countryName)
}

// ---------------------------------------------------------------- matching + scoring

function buildComparisonRow(sourceProduct, targetProduct, matchTier, sourceCountry, targetCountry, rates) {
  const sourceRate = sourceProduct.priceCurrency ? rates.get(sourceProduct.priceCurrency) : null
  const targetRate = targetProduct.priceCurrency ? rates.get(targetProduct.priceCurrency) : null
  // Both sides convert independently to USD — DIVIDE by the stored rate
  // (units of that currency per 1 USD), never multiply, and never convert
  // source currency straight to target currency; see
  // fetchMarketOpportunityExchangeRate's own doc-comment for why.
  const sourceNormalized =
    sourceProduct.perKgLocal != null && sourceRate?.available ? sourceProduct.perKgLocal / sourceRate.rate : null
  const targetNormalized =
    targetProduct.perKgLocal != null && targetRate?.available ? targetProduct.perKgLocal / targetRate.rate : null

  const reviewReasons = []
  if (matchTier === 'curated_override') {
    reviewReasons.push('Matched via a curated name override, not an identical name after translation/normalization — see crossCountryMatchOverrides.js.')
  }
  if (matchTier === 'hs_code') {
    reviewReasons.push(
      `Matched by shared HS code (${sourceProduct.hsCode}${sourceProduct.hsDescription ? `: ${sourceProduct.hsDescription}` : ''}), not an identical/translated name or a curated override — other product variants on either side may share this same code, so this pairing is one of possibly several.`,
    )
  }
  if (sourceProduct.perKgLocal == null) reviewReasons.push(`Source (${sourceCountry}): ${sourceProduct.unitComment}`)
  if (targetProduct.perKgLocal == null) reviewReasons.push(`Target (${targetCountry}): ${targetProduct.unitComment}`)
  if (sourceProduct.priceCurrency && !sourceRate?.available) {
    reviewReasons.push(`No USD exchange rate available for ${sourceProduct.priceCurrency} (source).`)
  }
  if (targetProduct.priceCurrency && !targetRate?.available) {
    reviewReasons.push(`No USD exchange rate available for ${targetProduct.priceCurrency} (target).`)
  }
  if (!sourceProduct.priceCurrency) reviewReasons.push(`Source (${sourceCountry}): no currency could be determined for this product.`)
  if (!targetProduct.priceCurrency) reviewReasons.push(`Target (${targetCountry}): no currency could be determined for this product.`)

  // A count-based unit converted to $/kg via countWeightConversion.js (see
  // that module's own header) — a Haiku-estimated conversion (cached or
  // fresh) is never presented with the same confidence as an exact-name
  // match, and an egg conversion that had to assume a default USDA size
  // class is flagged too, even though the underlying dozen-weight figure
  // itself is a real, official standard — the ASSUMPTION is what's
  // uncertain, not the reference table (see resolveEggPriceViaUsdaStandard).
  const conversionNotes = []
  ;[
    ['source', sourceProduct, sourceCountry],
    ['target', targetProduct, targetCountry],
  ].forEach(([side, product, countryName]) => {
    if (!product.conversionNote) return
    conversionNotes.push(`${side === 'source' ? 'Source' : 'Target'} (${countryName}): ${product.conversionNote}`)
    if (product.conversionMethod === 'cached_estimate' || product.conversionMethod === 'fresh_haiku_estimate') {
      reviewReasons.push(
        `${side === 'source' ? 'Source' : 'Target'} (${countryName}): converted from a count-based unit using an AI-estimated pack weight (Haiku, ${product.conversionMethod === 'cached_estimate' ? 'cached from an earlier estimate' : 'freshly estimated'}), not an official standard.`,
      )
    }
    if (product.assumedGradeDefault) {
      reviewReasons.push(
        `${side === 'source' ? 'Source' : 'Target'} (${countryName}): this product's own grading scale has no established correspondence to USDA's egg size classes — "Large" was assumed for the dozen-weight lookup, not a confirmed match.`,
      )
    }
  })
  const conversionNote = conversionNotes.length > 0 ? conversionNotes.join(' ') : null

  return {
    product_name: sourceProduct.displayName,
    source_country: sourceCountry,
    target_country: targetCountry,
    hs_code: sourceProduct.hsCode || null,
    source_price_value: sourceProduct.priceValue,
    source_price_unit: sourceProduct.priceUnit,
    source_price_currency: sourceProduct.priceCurrency,
    target_price_value: targetProduct.priceValue,
    target_price_unit: targetProduct.priceUnit,
    target_price_currency: targetProduct.priceCurrency,
    source_price_normalized: sourceNormalized,
    target_price_normalized: targetNormalized,
    exchange_rate_source_used: sourceRate?.rate ?? null,
    exchange_rate_source_date: sourceRate?.date ?? null,
    exchange_rate_target_used: targetRate?.rate ?? null,
    exchange_rate_target_date: targetRate?.date ?? null,
    match_tier: matchTier,
    review_reasons: reviewReasons,
    conversion_note: conversionNote,
    // Display-only fields the backend doesn't need to persist but the
    // results table wants without re-deriving:
    _target_display_name: targetProduct.displayName,
  }
}

// -------------------------------------------------- count-vs-weight conversion
//
// See countWeightConversion.js's own header for the full picture. This is
// the orchestration: find which matched-pair products actually need it
// (one side still unconvertible-because-count-based, the OTHER side
// already weight-resolved — the specific mismatch this exists for, not
// "every count-based product regardless of pairing"), resolve eggs for
// free/synchronously, and batch every other distinct product into ONE
// cached-Haiku-estimate request. A product object is mutated in place
// (perKgLocal/conversionNote/conversionMethod/assumedGradeDefault) the
// first time it's resolved — since sourceProducts/targetProducts arrays
// are shared across every target-country iteration in
// computeMarketOpportunity, this also means a product is never
// re-resolved twice within one run, on top of the backend's own
// forever-cache keeping it from ever being paid for twice across runs.

// Colombia's collector always sets BOTH rawUnit/rawUnitLabel (even when
// unitLabel itself is null, for a plain "kg" product) — so the key's
// PRESENCE, not its value, is what distinguishes Colombia's raw
// unit/unitLabel pair from a custom source's single rawUnit string. A USA
// product has neither key: its own count-based case (produce cartons) is
// already handled by a separate, dedicated research pathway
// (usaWeightResearchItem) and is out of scope here.
function classifyProductCountUnit(product) {
  if ('rawUnitLabel' in product) return classifyColombiaCountUnit(product.rawUnit, product.rawUnitLabel)
  if ('rawUnit' in product) return classifyGenericCountUnit(product.rawUnit)
  return null
}

async function resolveCountWeightConversions(pairs) {
  const genericCandidates = new Map() // signature -> { product, description }

  pairs.forEach(({ sp, tp }) => {
    ;[sp, tp].forEach((product, index) => {
      const counterpart = index === 0 ? tp : sp
      if (product.perKgLocal != null) return // already resolved (official, or a prior pair already converted it)
      if (counterpart.perKgLocal == null) return // the OTHER side isn't weight-resolved either — not this module's scope
      const countInfo = classifyProductCountUnit(product)
      if (!countInfo) return // null unit, volume unit, or anything else unitConversion.js/genericUnitConversion.js already explain — untouched

      if (isEggProduct(product.hsCode, product.displayName)) {
        const resolved = resolveEggPriceViaUsdaStandard(product.priceValue, countInfo.itemCount, countInfo.perSingleItem)
        if (resolved) {
          product.perKgLocal = resolved.perKg
          product.conversionNote = resolved.conversionNote
          product.conversionMethod = resolved.method
          product.assumedGradeDefault = resolved.assumedGradeDefault
        }
        return
      }

      // Unlike the egg formula above, the generic Haiku tier normally asks
      // for the WHOLE pack's weight directly (same convention as
      // usaWeightResearchItem/colombiaWeightResearchItem) — countInfo's
      // itemCount can be null here (a bare "Bag"/"Bundle"/"Head" with no
      // stated count) and this is still eligible; packDescription is all
      // the generic tier actually needs. countInfo.perSingleItem flips this
      // to asking for ONE item's weight instead (see
      // classifyColombiaCountUnit's own header) — carried onto the product
      // so the conversionNote below can describe what was actually asked.
      const signature = genericWeightSignature(product.displayName)
      if (!genericCandidates.has(signature)) {
        genericCandidates.set(signature, {
          products: [],
          description: buildGenericWeightDescription(product.displayName, countInfo.packDescription, countInfo.perSingleItem),
          perSingleItem: countInfo.perSingleItem,
        })
      }
      genericCandidates.get(signature).products.push(product)
    })
  })

  if (genericCandidates.size === 0) return

  const items = [...genericCandidates.entries()].map(([signature, entry]) => ({ signature, description: entry.description }))
  // Chunked at the backend's own MAX_ITEMS_PER_BATCH (25) — a real "By
  // Region" run could plausibly exceed that in one go; each chunk is its
  // own request so one large run never fails outright over a batch-size
  // limit meant for a single Haiku call.
  const CHUNK_SIZE = 25
  for (let i = 0; i < items.length; i += CHUNK_SIZE) {
    const chunk = items.slice(i, i + CHUNK_SIZE)
    // eslint-disable-next-line no-await-in-loop -- sequential chunks are deliberate: each is its own Haiku call, not worth parallelizing for a handful of chunks at most
    const { results } = await requestUnitWeightEstimates(chunk)
    chunk.forEach(({ signature }) => {
      const result = results[signature]
      const entry = genericCandidates.get(signature)
      if (!result || result.weight_grams == null) {
        entry.products.forEach((product) => {
          product.conversionNote = `AI (Haiku) could not estimate a typical pack weight for this product${result?.note ? `: ${result.note}` : '.'}`
        })
        return
      }
      const method = result.cached ? 'cached_estimate' : 'fresh_haiku_estimate'
      entry.products.forEach((product) => {
        // Each product in this signature group shares the SAME weight
        // estimate (same displayName), but keeps its own price — a
        // different source's row for the exact same product name still
        // divides its OWN price by the shared pack weight, never another
        // row's price.
        product.perKgLocal = resolveGenericPriceFromWeightGrams(product.priceValue, result.weight_grams)
        product.conversionNote =
          `Converted using a Haiku-estimated typical ${entry.perSingleItem ? 'single-item' : 'pack'} weight (${result.weight_grams.toFixed(0)} g` +
          `${result.note ? `: ${result.note}` : ''}) — an AI estimate, not an official standard.`
        product.conversionMethod = method
      })
    })
  }
}

// Computes (but does not yet persist) every source->target comparison row
// for one source country against one or more target countries — a Target =
// "By Region" run passes every qualifying country in that region, each run
// as its own independent source->target pair (spec's own natural extension
// of the one-source-vs-one-target case). Returns matched rows (ready to
// POST to saveMarketOpportunityComparisons) and, separately, every source
// product that found no match in a given target market — never dropped,
// never blended into the matched table, per spec.
export async function computeMarketOpportunity(sourceCountry, targetCountries) {
  const allCountries = [sourceCountry, ...targetCountries.filter((name) => name !== sourceCountry)]
  const [productsByCountry, hsCache] = await Promise.all([
    Promise.all(allCountries.map(async (name) => [name, await collectCountryComparisonProducts(name)])).then(
      (entries) => new Map(entries),
    ),
    fetchProductHsCodes().catch(() => ({ results: {} })),
  ])
  // Same cache key format the classification pipeline itself uses
  // everywhere else (buildProductPortfolio/buildCategoryCoverage): the
  // product's plain display name, trimmed and lowercased — NOT matchName,
  // which additionally strips accents/parentheticals for the name-join
  // above and so would miss real cache entries (e.g. "tomato (deli) (a)"
  // is cached under that exact string, parentheses and all).
  const hsByExactName = hsCache.results || {}
  productsByCountry.forEach((products) => {
    products.forEach((p) => {
      const hit = hsByExactName[p.displayName.trim().toLowerCase()]
      p.hsCode = hit?.hs_code || null
      p.hsDescription = hit?.description || null
    })
  })
  const sourceProducts = productsByCountry.get(sourceCountry) || []

  const currencies = new Set()
  productsByCountry.forEach((products) => products.forEach((p) => p.priceCurrency && currencies.add(p.priceCurrency)))
  const rates = new Map()
  await Promise.all(
    [...currencies].map(async (code) => {
      try {
        rates.set(code, await fetchMarketOpportunityExchangeRate(code))
      } catch {
        rates.set(code, { rate: null, date: null, available: false })
      }
    }),
  )

  const matchedPairs = []
  const unmatchedByTarget = {}
  targetCountries.forEach((targetCountry) => {
    const targetProducts = productsByCountry.get(targetCountry) || []
    const targetByName = new Map(targetProducts.map((p) => [p.matchName, p]))
    // Every target product sharing a given (real, classified) HS code —
    // tier 3's candidate pool. A product with no resolved code (not yet
    // classified) simply never appears in any group here.
    const targetByHsCode = new Map()
    targetProducts.forEach((p) => {
      if (!p.hsCode) return
      if (!targetByHsCode.has(p.hsCode)) targetByHsCode.set(p.hsCode, [])
      targetByHsCode.get(p.hsCode).push(p)
    })

    const unmatched = []
    sourceProducts.forEach((sp) => {
      // A single source product's own set of (sourceCountry, targetCountry)
      // pairs already produced, so tier 3 below never re-emits the exact
      // same pairing tier 1/2 already did — every OTHER same-code target
      // candidate still gets its own row (the user's explicit choice: every
      // combination shown, nothing picked for them).
      const pairedTargetNames = new Set()
      let matchedAny = false

      const overrideName = lookupCrossCountryOverride(sourceCountry, targetCountry, sp.matchName)
      const nameMatch = (overrideName && targetByName.get(overrideName)) || targetByName.get(sp.matchName)
      if (nameMatch) {
        const matchTier = overrideName ? 'curated_override' : sp.translated ? 'translated_exact' : 'exact'
        matchedPairs.push({ sp, tp: nameMatch, matchTier, targetCountry })
        pairedTargetNames.add(nameMatch.matchName)
        matchedAny = true
      }

      if (sp.hsCode) {
        const candidates = targetByHsCode.get(sp.hsCode) || []
        candidates.forEach((tp) => {
          if (pairedTargetNames.has(tp.matchName)) return
          matchedPairs.push({ sp, tp, matchTier: 'hs_code', targetCountry })
          pairedTargetNames.add(tp.matchName)
          matchedAny = true
        })
      }

      if (!matchedAny) unmatched.push(sp)
    })
    unmatchedByTarget[targetCountry] = unmatched
  })

  // Count-vs-weight conversion (countWeightConversion.js) runs AFTER
  // matching, on the real matched pairs only — never speculatively on
  // every count-based product regardless of whether it's actually part of
  // a real comparison, which is both wasted Haiku spend and outside this
  // mechanism's own stated scope (see that module's header).
  await resolveCountWeightConversions(matchedPairs)

  const rows = matchedPairs.map(({ sp, tp, matchTier, targetCountry }) => buildComparisonRow(sp, tp, matchTier, sourceCountry, targetCountry, rates))

  return { rows, unmatchedByTarget, sourceProductCount: sourceProducts.length }
}
