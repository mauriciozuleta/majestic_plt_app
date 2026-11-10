// General Portfolio Directory and Available Categories. Both are built on the SERVER now (backend/portfolio/, routers/portfolio.py): this file only asks for them.
// It used to collect every country's products, merge Colombia's two sources, translate the names and roll the HS codes up in the browser; a parity test
// (backend/tests/test_portfolio_parity.py) holds the Python to exactly that old output.
//
// The directory has ONE ROW PER COUNTRY AND PRODUCT. A product's code is "<ISO2 of the country it is sold in><6-digit HS code>" (e.g. Jamaica tomato -> "JM070200"), taken from
// the `hs` block the normalization module puts on every stored product. There are NO placeholder codes: a product without an HS code has code null and label "no_code";
// a code that is only a 4-digit heading padded with zeros has label "heading_only". Asking for the directory never starts a classification (that is an explicit step,
// routers/hs_codes.py), so viewing a page never spends credits.
import { API_BASE } from './apiBase'

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

/** One row per country and product: { code, name, category, country, countries: [country], hs, label } — `code` and `hs` are null when the product has no HS code
 * ("label" is then 'no_code'); `label` is 'heading_only' for a padded 4-digit heading and 'ok' otherwise. */
export async function buildProductPortfolio() {
  const { rows } = await fetchJson('/api/portfolio/directory')
  return rows
}

/** Available Categories: { [chapter]: { wholesaler: [iso2], retail: [iso2], productCount, countries, headings: { [heading]: { wholesaler, retail, subheadings: { [sub]: { wholesaler, retail } } } } } }.
 * Only chapters / headings / subheadings with at least one product that has an HS code appear. A country's ISO2 is in ONE bucket per product — the deepest level its
 * code reaches — split wholesaler / retail by the product's own source. The keys are the chapters SAM and TAM cover. */
export async function buildCategoryCoverage() {
  return fetchJson('/api/portfolio/category-coverage')
}
