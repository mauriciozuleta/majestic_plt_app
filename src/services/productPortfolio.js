// General Portfolio Directory — every product of every country's portfolio, ONE ROW PER COUNTRY AND PRODUCT, alphabetized. A product's code is
// "<ISO2 of the country it is sold in><6-digit HS code>" (e.g. Jamaica tomato -> "JM070200"), taken from the `hs` block the backend's normalization module puts on
// every stored product (backend/catalog_normalization/hs.py). There are NO placeholder codes: a product without an HS code has code null and the label "no_code",
// a code that is only a 4-digit heading padded with zeros has the label "heading_only". Opening this never starts a classification (that is an explicit step:
// routers/hs_codes.py), so viewing a page never spends credits.
//
// Recomputed from the live snapshot data each time it is needed — deliberately not cached or persisted. Built on the frontend for now only because Colombia's
// Spanish names are translated by the dictionary (productTranslations.js) before display; the codes themselves come from the backend.

import { mergeSources } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData'
import { translateProductName } from '../components/company/tabs/OperationsTab/MarketAnalysis/productTranslations'
import { fetchPriceComparisonSnapshot, fetchTranslationOverrides } from '../components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonFetchers'
import { fetchUsaSourcingSnapshot } from '../components/company/tabs/OperationsTab/MarketAnalysis/usaSourcingFetchers'
import { fetchCustomSourceProducts, fetchProductSources } from './productSources'
import { fetchReferenceCountries } from './commercialStructure'

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
    hs: p.hs ?? null,
  }))
}

async function collectUsaProducts() {
  const snapshots = await fetchUsaSourcingSnapshot()
  return snapshots.flatMap((s) => s.products.map((p) => ({ name: p.product_en, category: p.category, sourceIds: [s.source], hs: p.hs ?? null })))
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
    products: source.products.map((p) => ({ name: p.name, category: p.category, sourceIds: [source.source_id], hs: p.hs ?? null })),
  }))
  return [
    { countryName: 'Colombia', products: colombia },
    { countryName: 'United States', products: usa },
    ...customSources,
  ]
}

/** One row per country and product: { code, name, category, country, countries: [country], hs, label } — `code` and `hs` are null when the product has no HS code
 * ("label" is then 'no_code'); `label` is 'heading_only' for a padded 4-digit heading and 'ok' otherwise. */
export async function buildProductPortfolio() {
  const sources = await collectAllSources()

  const byKey = new Map()
  sources.forEach(({ countryName, products }) => {
    products.forEach(({ name, category, hs }) => {
      const trimmed = (name || '').trim()
      if (!trimmed) return
      const key = `${countryName.toLowerCase()}|${trimmed.toLowerCase()}`
      if (!byKey.has(key)) byKey.set(key, { name: trimmed, category, country: countryName, hs: hs ?? null })
      else if (!byKey.get(key).hs?.hs6 && hs?.hs6) byKey.get(key).hs = hs
    })
  })

  return Array.from(byKey.values())
    .sort((a, b) => a.name.localeCompare(b.name) || a.country.localeCompare(b.country))
    .map((row) => ({
      code: row.hs?.code ?? null,
      name: row.name,
      category: categoryInfo(row.category).label,
      country: row.country,
      countries: [row.country],
      hs: row.hs,
      label: row.hs?.label ?? 'no_code',
    }))
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
  const [sources, referenceCountries, productSources] = await Promise.all([
    collectAllSources(),
    fetchReferenceCountries().catch(() => []),
    fetchProductSources().catch(() => ({ built_in: [], custom: [] })),
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

  const chapters = new Map()

  sources.forEach(({ countryName, products }) => {
    const countryCode = countryCodeByName.get((countryName || '').toLowerCase())
    if (!countryCode) return
    products.forEach(({ name, sourceIds, hs }) => {
      const trimmed = (name || '').trim()
      if (!trimmed) return
      if (!hs?.hs6) return // no HS code yet: not part of any category
      const code = hs.hs6
      const chapterCode = code.slice(0, 2)
      const headingCode = code.slice(0, 4)
      // a code that is only a padded 4-digit heading belongs to the heading, not to a made-up subheading
      const subheadingCode = hs.level === 4 ? null : code.slice(0, 6)

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
