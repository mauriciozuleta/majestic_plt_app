// General Portfolio Directory — every distinct product name across every
// country's product portfolio, deduplicated (the same product sourced from
// 3 countries appears once), alphabetized, with a reference code. Recomputed
// fresh from the live snapshot data each time it's needed — deliberately
// not cached/persisted, since that's the simplest way to keep it "always
// current" without a separate update-trigger mechanism. Shared (not tab-
// specific) because three places need it: Documentation's own directory
// listing, and each country's own Product Analysis table showing its own
// products' codes.
//
// Built on the frontend, not the backend, because product names need to be
// in English for this to be useful as a single cross-country reference —
// Colombia's raw data is Spanish, and the Spanish->English dictionary
// (productTranslations.js) is a frontend-only concern by design (see its
// own header comment). Duplicating that dictionary server-side would be a
// second copy that could drift from the real one.
//
// A product's code is its country's ISO2 code + its real UN Comtrade HS
// code (e.g. onions from Colombia -> "CO070310") — classified once per
// product name and cached permanently server-side (see
// backend/comtrade/product_classification.py), not recomputed here. A
// product that couldn't be confidently classified falls back to the old
// country+category+sequence scheme instead of guessing a wrong HS code.

import { mergeSources } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData'
import { translateProductName } from '../components/company/tabs/OperationsTab/MarketAnalysis/productTranslations'
import { fetchPriceComparisonSnapshot, fetchTranslationOverrides } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'
import { fetchCustomSourceProducts, fetchProductSources } from './productSources'
import { fetchProductHsCodes, startProductClassification } from './productHsCodes'
import { fetchCommercialCountries, fetchReferenceCountries } from './commercialStructure'
import { useAppStore } from '../store/useAppStore'

// Same category concept gets the same 2-letter code regardless of which
// country/source uses which name for it (Colombia's "Carnicos" and the
// USA's "Beef" both become "BE") — chosen to avoid collisions between
// genuinely different categories (Pork "PK" vs Poultry "PO"). Used only as
// the fallback scheme now, for a product an HS code couldn't be assigned to.
const CATEGORY_CODES = {
  pollo: { code: 'PO', label: 'Poultry' },
  pescados_mariscos: { code: 'FI', label: 'Fish & Seafood' },
  platanos: { code: 'PL', label: 'Plantains' },
  tuberculos: { code: 'TU', label: 'Tubers' },
  frutas: { code: 'FR', label: 'Fruits' },
  hortalizas: { code: 'VE', label: 'Vegetables' },
  carnicos: { code: 'BE', label: 'Beef' },
  huevos: { code: 'EG', label: 'Eggs' },
  lacteos: { code: 'DA', label: 'Dairy' },
  granos_procesados: { code: 'GR', label: 'Grains & Processed' },
  Beef: { code: 'BE', label: 'Beef' },
  Pork: { code: 'PK', label: 'Pork' },
  Poultry: { code: 'PO', label: 'Poultry' },
  Eggs: { code: 'EG', label: 'Eggs' },
  'Grains (Export)': { code: 'GR', label: 'Grains (Export)' },
  'Produce (FL Shipping Point)': { code: 'PF', label: 'Produce (FL)' },
  'Produce (CA Shipping Point)': { code: 'PC', label: 'Produce (CA)' },
}

function categoryInfo(rawCategory) {
  if (CATEGORY_CODES[rawCategory]) return CATEGORY_CODES[rawCategory]
  const letters = (rawCategory || '').replace(/[^A-Za-z]/g, '').toUpperCase()
  return { code: letters.slice(0, 2) || 'XX', label: rawCategory || 'Uncategorized' }
}

async function collectColombiaProducts() {
  // Overrides included so a product's translated name here — and so its
  // lookup key in the code index below — exactly matches what
  // ColombiaProductAnalysisView itself displays and looks its own code up
  // by (see translateProductName(nameEs, translationOverrides) there).
  // Without this, a name resolved only via a manual/AI-confirmed override
  // (not yet in the static dictionary) would build its code under one
  // string here but be looked up under the same string correctly there —
  // that part's fine — the real risk was drift if the two ever computed
  // the translation differently; fetching overrides in both places keeps
  // them identical by construction.
  const [snapshots, overrides] = await Promise.all([
    fetchPriceComparisonSnapshot(),
    fetchTranslationOverrides().catch(() => []),
  ])
  const overridesByKey = Object.fromEntries(overrides.map((row) => [row.product_key, row.translation_en]))
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  if (!bySource.la_mayorista && !bySource.corabastos) return []
  const merged = mergeSources(bySource.la_mayorista || [], bySource.corabastos || [])
  // sourceIds: which of the two built-in Colombia sources actually carried
  // this product — derived from which merged price field is non-null,
  // since mergeSources() combines both into one row per product id and
  // that's the only place the distinction survives. A product can have
  // both (priced by both sources), so this is an array, not a single id —
  // needed by buildCategoryCoverage() below since la_mayorista/corabastos
  // each have their own independent Wholesaler/Retail label.
  return merged.map((p) => ({
    name: translateProductName(p.nameEs, overridesByKey).text,
    category: p.category,
    sourceIds: [p.laMayorista != null ? 'la_mayorista' : null, p.corabastos != null ? 'corabastos' : null].filter(Boolean),
  }))
}

async function collectUsaProducts() {
  const snapshots = await fetchUsaSourcingSnapshot()
  return snapshots.flatMap((s) => s.products.map((p) => ({ name: p.product_en, category: p.category, sourceIds: [s.source] })))
}

// Each product-portfolio source contributes {countryName, products}: the
// two built-in pipelines (Colombia, USA) plus every source added in
// Settings ▸ Product analysis sources.
async function collectAllSources() {
  const [colombia, usa, custom] = await Promise.all([
    collectColombiaProducts().catch(() => []),
    collectUsaProducts().catch(() => []),
    fetchCustomSourceProducts().catch(() => []),
  ])
  // Sources added in Settings: each one's products join its country's list.
  const customSources = custom.map((source) => ({
    countryName: source.country_name,
    products: source.products.map((p) => ({ name: p.name, category: p.category, sourceIds: [source.source_id] })),
  }))
  return [
    { countryName: 'Colombia', products: colombia },
    { countryName: 'United States', products: usa },
    ...customSources,
  ]
}

// A country's ISO2 code, across EVERY company — not just whichever
// company's tab this happens to be viewed from. The old per-company lookup
// (only that company's own commercial countries) silently fell back to
// "XX" for a product sourced from a country a DIFFERENT company owns (e.g.
// viewing Documentation from FRESH24, whose own commercial structure
// doesn't include Colombia — that belongs to FRESH24-Colombia).
async function buildGlobalCountryCodeMap() {
  const companies = useAppStore.getState().companies
  const lists = await Promise.all(companies.map((company) => fetchCommercialCountries(company.id).catch(() => [])))
  const map = new Map()
  lists.flat().forEach((country) => {
    if (country.country_code) map.set(country.name.toLowerCase(), country.country_code)
  })
  return map
}

export async function buildProductPortfolio() {
  const [sources, countryCodeByName] = await Promise.all([collectAllSources(), buildGlobalCountryCodeMap()])

  const byKey = new Map()
  sources.forEach(({ countryName, products }) => {
    products.forEach(({ name, category }) => {
      const trimmed = (name || '').trim()
      if (!trimmed) return
      const key = trimmed.toLowerCase()
      if (!byKey.has(key)) {
        byKey.set(key, { name: trimmed, category, countries: [] })
      }
      const entry = byKey.get(key)
      if (!entry.countries.includes(countryName)) entry.countries.push(countryName)
    })
  })

  const rows = Array.from(byKey.values()).sort((a, b) => a.name.localeCompare(b.name))

  // Whatever's already been classified is instant (a table read); anything
  // new is queued for background classification and shown with the old
  // fallback code THIS time — never blocked on here, since classifying a
  // large new batch can take minutes (see productHsCodes.js). It'll have
  // its real HS code the next time this loads.
  let hsByName = {}
  try {
    const { results } = await fetchProductHsCodes()
    hsByName = results
    const uncached = rows.filter((row) => !(row.name.toLowerCase() in hsByName))
    if (uncached.length > 0) {
      // Category and country go along as context: a cut name alone ("Primal
      // Belly", "Drumsticks") doesn't say which animal it is, and a regional
      // name ("coco" in Jamaica = cocoyam) depends on where it's sold.
      startProductClassification(
        uncached.map((row) => ({
          key: row.name.toLowerCase(),
          name: row.name,
          context: `${categoryInfo(row.category).label}; sold in ${row.countries.join(', ')}`,
        })),
      ).catch(() => {})
    }
  } catch {
    // Couldn't even read the cache (offline, etc.) — every row falls back
    // to the old scheme below rather than blocking the directory.
  }

  return rows.map((row, index) => {
    const primaryCountry = row.countries[0]
    const countryCode = countryCodeByName.get(primaryCountry.toLowerCase()) || 'XX'
    const hs = hsByName[row.name.toLowerCase()]
    const { code: categoryCode, label: categoryLabel } = categoryInfo(row.category)
    const sequence = String(index + 1).padStart(3, '0')
    return {
      // A real HS code when one was confidently assigned (e.g. onions from
      // Colombia -> "CO070310"); the old country+category+sequence scheme
      // for anything that couldn't be classified, so every product still
      // gets a stable, unique code either way.
      code: hs ? `${countryCode}${hs.hs_code}` : `${countryCode}${categoryCode}${sequence}`,
      name: row.name,
      category: categoryLabel,
      countries: row.countries,
    }
  })
}

/** Convenience for a single country's Product Analysis table: the same
 * portfolio, as a lookup from normalized (lowercase, trimmed) product name
 * straight to its code — so a table doesn't need to hold the whole
 * portfolio just to look up its own rows' codes. */
export async function buildProductCodeIndex() {
  const portfolio = await buildProductPortfolio()
  return new Map(portfolio.map((row) => [row.name.toLowerCase(), row.code]))
}

function emptyBucketPair() {
  return { wholesaler: new Set(), retail: new Set() }
}

function addToBucketPair(pair, analysisType, countryCode) {
  const bucket = analysisType === 'retail' ? pair.retail : pair.wholesaler
  bucket.add(countryCode)
}

/** Available Categories: for every real product across every country's
 * product catalog (both built-in Colombia/USA pipelines and every custom
 * source added in Settings), rolls its classified HS code up to
 * chapter/heading/subheading, tagging each level with the distinct ISO
 * alpha-2 country codes that actually have a product there — split into
 * Wholesaler/Retail by that product's own source's analysis_type. Computed
 * on the frontend, not the backend, for the same reason buildProductPortfolio
 * above is: Colombia's raw product names are Spanish, and the Spanish-English
 * dictionary (productTranslations.js) that resolves them to the same English
 * name product_hs_codes is keyed by is a frontend-only concern by design —
 * the backend has no way to reproduce that lookup on its own. Returns
 * {[chapter]: {wholesaler: [iso2...], retail: [iso2...], productCount,
 * countries: [iso2...], headings: {[heading]: {wholesaler, retail,
 * subheadings: {[subheading]: {wholesaler, retail}}}}}} — only chapters/
 * headings/subheadings that actually have at least one classified product
 * appear at all (never the full HS reference tree). A product with no
 * confident HS classification yet (see product_classification.py) is
 * simply skipped — it'll appear once background classification catches up.
 *
 * A chapter's own `productCount`/`countries` are its section-summary
 * numbers — every distinct product classified anywhere under that chapter
 * (any heading/subheading) and every distinct country carrying one,
 * combining wholesaler and retail alike. These are independent of the
 * per-level wholesaler/retail buckets below (which are leaf-only, see
 * next paragraph) — a chapter can have real products and so a non-zero
 * productCount/countries even though its own wholesaler/retail arrays are
 * empty, because that coverage lives one or more levels deeper.
 *
 * A country's ISO2 code is only ever placed in ONE wholesaler/retail
 * bucket per product — the deepest level that product's own classification
 * reaches (subheading when 6+ digits, otherwise the heading) — never
 * cascaded up to the chapter/heading as well. A chapter or heading with no
 * product reaching exactly that level still appears (matched/green,
 * expandable) with an empty wholesaler/retail array of its own; its
 * country coverage lives one or more levels deeper instead.
 */
export async function buildCategoryCoverage() {
  const [sources, referenceCountries, productSources, hsCache] = await Promise.all([
    collectAllSources(),
    fetchReferenceCountries().catch(() => []),
    fetchProductSources().catch(() => ({ built_in: [], custom: [] })),
    fetchProductHsCodes().catch(() => ({ results: {} })),
  ])

  const countryCodeByName = new Map(referenceCountries.map((c) => [c.name.toLowerCase(), c.country_code]))
  // Every source's analysis_type, built-in and custom alike, keyed by the
  // same source id each product above was tagged with (la_mayorista,
  // usa_beef, or a custom source's own uuid) — so a product's Wholesaler/
  // Retail bucket always reflects its OWN source's current label, not a
  // guess, matching Settings ▸ Product analysis sources exactly.
  const analysisTypeBySourceId = Object.fromEntries([
    ...productSources.built_in.map((s) => [s.id, s.analysis_type]),
    ...productSources.custom.map((s) => [s.id, s.analysis_type]),
  ])
  const hsByName = hsCache.results || {}

  const chapters = new Map()

  sources.forEach(({ countryName, products }) => {
    const countryCode = countryCodeByName.get((countryName || '').toLowerCase())
    if (!countryCode) return
    products.forEach(({ name, sourceIds }) => {
      const trimmed = (name || '').trim()
      if (!trimmed) return
      const hs = hsByName[trimmed.toLowerCase()]
      if (!hs || !hs.hs_code) return
      const code = hs.hs_code
      const chapterCode = code.slice(0, 2)
      const headingCode = code.slice(0, 4)
      const subheadingCode = code.length >= 6 ? code.slice(0, 6) : null

      if (!chapters.has(chapterCode))
        chapters.set(chapterCode, { ...emptyBucketPair(), headings: new Map(), products: new Set(), countries: new Set() })
      const chapter = chapters.get(chapterCode)
      // Tracked at the chapter level regardless of which leaf bucket claims
      // the country code above — this is what the section-header summary
      // ("N products in M countries") is built from, and a product only
      // ever classifies into exactly one chapter, so summing productCount
      // across a section's chapters can never double-count.
      chapter.products.add(trimmed.toLowerCase())
      chapter.countries.add(countryCode)

      if (!chapter.headings.has(headingCode)) chapter.headings.set(headingCode, { ...emptyBucketPair(), subheadings: new Map() })
      const heading = chapter.headings.get(headingCode)

      let subheading = null
      if (subheadingCode) {
        if (!heading.subheadings.has(subheadingCode)) heading.subheadings.set(subheadingCode, emptyBucketPair())
        subheading = heading.subheadings.get(subheadingCode)
      }

      // A product can belong to more than one source at once (e.g. priced
      // by both La Mayorista and Corabastos) — each contributes to its own
      // bucket independently, deduped by the Set either way.
      //
      // The country code is added to exactly ONE bucket: the deepest level
      // this product's own classification actually reaches (the subheading
      // when its HS code is 6+ digits, otherwise the heading — a 4-digit-
      // only classification, see product_classification.py). It is
      // deliberately never added to the chapter bucket here — a chapter
      // still shows as matched/green and stays expandable (the Maps above
      // are populated regardless), it just doesn't claim the country's code
      // as its own when that code really belongs to a more specific row.
      const target = subheading || heading
      ;(sourceIds && sourceIds.length > 0 ? sourceIds : [null]).forEach((sourceId) => {
        const analysisType = analysisTypeBySourceId[sourceId] || 'wholesaler'
        addToBucketPair(target, analysisType, countryCode)
      })
    })
  })

  const toArray = (set) => Array.from(set).sort()
  const result = {}
  Array.from(chapters.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .forEach(([chapterCode, chapter]) => {
      const headings = {}
      Array.from(chapter.headings.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .forEach(([headingCode, heading]) => {
          const subheadings = {}
          Array.from(heading.subheadings.entries())
            .sort(([a], [b]) => a.localeCompare(b))
            .forEach(([subheadingCode, subheading]) => {
              subheadings[subheadingCode] = { wholesaler: toArray(subheading.wholesaler), retail: toArray(subheading.retail) }
            })
          headings[headingCode] = { wholesaler: toArray(heading.wholesaler), retail: toArray(heading.retail), subheadings }
        })
      result[chapterCode] = {
        wholesaler: toArray(chapter.wholesaler),
        retail: toArray(chapter.retail),
        headings,
        productCount: chapter.products.size,
        countries: toArray(chapter.countries),
      }
    })
  return result
}
