// Reads the `norm` block the backend's catalog normalization module (backend/catalog_normalization/) adds to every stored catalog product:
// { price_per_kg, pack_weight_kg, items_per_pack, item_kg, price_per_item, method, confidence, note, sources, read_name, read_unit, name_en }, in the product's own
// currency. It is the ONLY place a price becomes a price per kg: the tables, the product portfolio and Market Opportunities all read this value.
import { applyCustomOverride } from '../components/company/tabs/OperationsTab/MarketAnalysis/unitConversion'

export function normPerKg(norm) {
  return norm && typeof norm.price_per_kg === 'number' && Number.isFinite(norm.price_per_kg) ? norm.price_per_kg : null
}

// The comment explaining the figure: the module's note when it produced the figure, else `fallback` (why there is none).
export function commentWithFallback(norm, fallback) {
  if (normPerKg(norm) != null && norm.note) return norm.note
  return norm?.note || fallback
}

// A conversion that rests on a web-researched item weight (not on a weight written in the data or an official factor) is shown with its confidence.
export function isResearchedConversion(norm) {
  return norm?.method === 'researched_item_weight'
}

// A conversion that rests on USDA's published household weights (backend/catalog_normalization/reference.py): no AI, but still an average item, so it is flagged.
export function isReferenceConversion(norm) {
  return norm?.method === 'reference_item_weight'
}

// A table row's effective price per kg and its explanation: the module's figure, with a user's custom override (a price and/or weight typed by hand) on top.
// -> { perKg, researched, comment, note, sources, custom? }
export function resolveFromNorm(price, norm, override) {
  const perKg = normPerKg(norm)
  const base = {
    perKg,
    researched: isResearchedConversion(norm),
    reference: isReferenceConversion(norm),
    comment: commentWithFallback(norm, 'This price could not be converted to a price per kg.'),
    note: isResearchedConversion(norm) || isReferenceConversion(norm) ? norm.note : null,
    sources: norm?.sources ?? [],
  }
  return applyCustomOverride(price, base, override)
}

// The product names (as the module reads them) still waiting for a researched item weight.
export function missingResearchNames(norms) {
  return [...new Set(norms.filter((norm) => norm?.method === 'needs_research' && norm.read_name).map((norm) => norm.read_name))]
}
