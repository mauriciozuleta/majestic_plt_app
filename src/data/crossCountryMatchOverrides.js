// Curated SOURCE-country -> TARGET-country product-name overrides for
// Market Opportunities' cross-country price comparison (see
// services/marketOpportunities.js) — the exact same pattern as
// backend/price_sources/match_table.py's CORABASTOS_TO_LA_MAYORISTA_ID
// ("a human comparing both real product lists, never a fuzzy-string-match
// algorithm" — see that file's own header comment), generalized from its
// one hardcoded same-country/same-language pair (Corabastos <-> La
// Mayorista, both Colombia/Spanish) to arbitrary source/target COUNTRY
// pairs, since a cross-country comparison has no single shared source file
// to hardcode a pair-specific table into.
//
// Only entries where the two countries' MATCH names (English, after
// Colombia's translateProductName() step where it applies, then
// normalizeProductName()'s accent-strip/lowercase/parenthetical-strip —
// see marketOpportunities.js) genuinely differ for the same real product
// need to be listed here; identical match names already join automatically
// as an "exact" (or "translated_exact") match with no override needed.
//
// Keyed by "<Source Country>|<Target Country>": { normalizedSourceName:
// normalizedTargetName }. A starting point, not exhaustive — extend it as
// more real overlaps are confirmed by a human comparing both countries'
// actual product lists side by side, exactly like match_table.py's own
// header comment asks of it. A match made through this table is flagged
// with match_tier: 'curated_override' and carried into the comparison
// row's match_confidence as non-"confirmed" (see
// backend/routers/market_opportunities.py), same as match_table.py's own
// matches are never treated as more certain than what a human actually
// verified.

export const CROSS_COUNTRY_MATCH_OVERRIDES = {
  // Confirmed by a human comparing Colombia's real La Mayorista/Corabastos
  // catalog against Jamaica's real moa.gov.jm bulletin (both loaded live in
  // this app): Colombia's "Pimentón" translates to "Bell Pepper"
  // (productTranslations.js) -> normalizes to "bell pepper"; Jamaica's
  // bulletin instead calls the same real vegetable "Sweet Pepper", listed
  // per color ("Sweet Pepper (Green)", "(Red)", "(Yellow)") — every color
  // variant using PARENTHESES normalizes to the same "sweet pepper" (the
  // color qualifier is stripped by normalizeProductName, same as any other
  // parenthetical grade note), so this one override resolves all of them.
  // (Jamaica's bulletin also has a second, bracket-qualified spelling for
  // the same vegetable — "Sweet Pepper [Green] (Local)" etc — which does
  // NOT collapse the same way since normalizeProductName only strips
  // parentheses, not brackets; that's a real inconsistency in the source
  // data itself, not something to paper over here.)
  'Colombia|Jamaica': { 'bell pepper': 'sweet pepper' },
}

export function lookupCrossCountryOverride(sourceCountry, targetCountry, normalizedSourceName) {
  const table = CROSS_COUNTRY_MATCH_OVERRIDES[`${sourceCountry}|${targetCountry}`]
  return table ? table[normalizedSourceName] || null : null
}
