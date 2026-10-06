import { buildProductPortfolio } from './productPortfolio'
import { fetchMarketOpportunityComparisons, fetchMarketOpportunityPairs } from './marketOpportunities'
import { addRagFile } from './ragFiles'

// Builds each country's "Product Portfolio" and "Product Opportunities"
// documents (Markdown) from the live app data and adds them to that
// country's RAG Files folder — to be Loaded and Baked like any other file.
// Built here, not on the backend, because the portfolio's English product
// names come from the frontend-only translation dictionary (see
// productPortfolio.js). Re-running replaces the files; unchanged content
// leaves a file's Loaded/Baked status as it was.

const RATING_ORDER = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable']

// Windows-1252 code points for bytes 0x80-0x9f, to undo text that was UTF-8
// decoded as Windows-1252 ("â€”" for "—"), which some saved review notes have.
const WIN1252 = { 0x20ac: 0x80, 0x201a: 0x82, 0x0192: 0x83, 0x201e: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87, 0x02c6: 0x88, 0x2030: 0x89, 0x0160: 0x8a, 0x2039: 0x8b, 0x0152: 0x8c, 0x017d: 0x8e, 0x2018: 0x91, 0x2019: 0x92, 0x201c: 0x93, 0x201d: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97, 0x02dc: 0x98, 0x2122: 0x99, 0x0161: 0x9a, 0x203a: 0x9b, 0x0153: 0x9c, 0x017e: 0x9e, 0x0178: 0x9f }

function fixMojibake(text) {
  if (!text || !/[âÃ]/.test(text)) return text || ''
  try {
    const bytes = Uint8Array.from([...text].map((char) => WIN1252[char.charCodeAt(0)] ?? char.charCodeAt(0)))
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return text
  }
}

const usd = (value) => (value == null ? 'n/a' : `USD ${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/kg`)
const day = (iso) => (iso ? iso.slice(0, 10) : 'unknown date')

function portfolioDocument(country, rows) {
  const byCategory = new Map()
  rows.forEach((row) => byCategory.set(row.category, [...(byCategory.get(row.category) || []), row]))
  const lines = [
    `# ${country} — Product Portfolio`,
    '',
    `The ${rows.length} products in ${country}'s product portfolio (the products it is priced for in Majestic's market analysis), grouped by category. Each product has its portfolio reference code: the ISO country code followed by the UN Comtrade HS code when one was assigned.`,
    '',
  ]
  ;[...byCategory]
    .sort(([a], [b]) => a.localeCompare(b))
    .forEach(([category, items]) => {
      lines.push(`## ${category} (${items.length} products)`, '')
      items.forEach((item) => {
        const others = item.countries.filter((name) => name.toLowerCase() !== country.toLowerCase())
        lines.push(`- ${item.name} — code ${item.code}${others.length > 0 ? ` — also in: ${others.join(', ')}` : ''}`)
      })
      lines.push('')
    })
  return lines.join('\n')
}

function opportunityDocument(country, asTarget, asSource) {
  const lines = [
    `# ${country} — Product Opportunities`,
    '',
    `Price-gap opportunities saved in Majestic's Market Opportunities for ${country}: what is cheaper to source elsewhere than it sells for in ${country}, and what ${country} could supply to other markets. Prices are per kg in USD. Each product shows the source price as a percentage of the target market's price (the lower, the larger the margin). The rating follows from that percentage: Very High below 20%, High 20-30%, Challenging 30-50%, Complex 50-65%, Difficult 65-100%, Not Viable above 100% (the source costs more than the target market). "Review" means the match or conversion needs a human check.`,
    '',
  ]
  const section = (title, intro, groups) => {
    if (groups.length === 0) return
    lines.push(`## ${title}`, '', intro, '')
    groups.forEach(({ pair, rows }) => {
      lines.push(`### ${pair.source_country} to ${pair.target_country} (prices of ${day(pair.calculated_at)})`, '')
      RATING_ORDER.forEach((rating) => {
        const items = rows.filter((row) => row.opportunity_rating === rating).sort((a, b) => (a.diff_pct ?? 0) - (b.diff_pct ?? 0))
        if (items.length === 0) return
        lines.push(`#### ${rating} opportunity — ${pair.source_country} to ${pair.target_country} (${items.length} products)`, '')
        items.forEach((row) => {
          const share = row.diff_pct == null ? 'n/a' : `${row.diff_pct.toFixed(0)}%`
          const matched = row.target_product_name && row.target_product_name !== row.product_name ? ` (matched to "${row.target_product_name}")` : ''
          lines.push(
            `- ${row.product_name}${matched}${row.hs_code ? ` — HS ${row.hs_code}` : ''}: ${pair.source_country} ${usd(row.source_price_normalized)}, ${pair.target_country} ${usd(row.target_price_normalized)} — source is ${share} of the target price${row.match_confidence === 'confirmed' ? '' : ' — review'}`,
          )
          if (row.match_confidence !== 'confirmed' && row.review_reasons?.length) lines.push(`  - Review: ${row.review_reasons.map(fixMojibake).join(' ')}`)
        })
        lines.push('')
      })
    })
  }
  section(`Selling into ${country}`, `Products that can be sourced in another country and sold in ${country} at a higher price.`, asTarget)
  section(`Supplying from ${country}`, `Products priced in ${country} that sell for more in another market.`, asSource)
  return lines.join('\n')
}

/** Adds "<Country> - Product Portfolio.md" and "<Country> - Product Opportunities.md"
 * to each of the given RAG countries that has that data. onProgress(text) reports each step.
 * Returns [{ country, file, ok, error? }]. */
export async function addPortfolioAndOpportunityFiles(ragCountries, onProgress = () => {}) {
  const results = []
  onProgress('Building the product portfolios…')
  const portfolio = await buildProductPortfolio()
  const { pairs } = await fetchMarketOpportunityPairs()
  const rowsByPair = new Map()
  for (const pair of pairs) {
    onProgress(`Reading opportunities ${pair.source_country} → ${pair.target_country}…`)
    const data = await fetchMarketOpportunityComparisons(pair.source_country, [pair.target_country])
    rowsByPair.set(
      `${pair.source_country}>${pair.target_country}`,
      data.rows.filter((row) => row.target_country === pair.target_country),
    )
  }

  const add = async (country, file, text) => {
    onProgress(`Adding ${file}…`)
    try {
      await addRagFile(country, new File([text], file, { type: 'text/markdown' }))
      results.push({ country, file, ok: true })
    } catch (error) {
      results.push({ country, file, ok: false, error: error.message })
    }
  }

  for (const country of ragCountries) {
    const rows = portfolio.filter((row) => row.countries.some((name) => name.toLowerCase() === country.toLowerCase()))
    if (rows.length > 0) await add(country, `${country} - Product Portfolio.md`, portfolioDocument(country, rows))

    const group = (side) =>
      pairs
        .filter((pair) => pair[side].toLowerCase() === country.toLowerCase())
        .map((pair) => ({ pair, rows: rowsByPair.get(`${pair.source_country}>${pair.target_country}`) || [] }))
        .filter(({ rows: items }) => items.some((row) => row.opportunity_rating))
    const asTarget = group('target_country')
    const asSource = group('source_country')
    if (asTarget.length + asSource.length > 0) await add(country, `${country} - Product Opportunities.md`, opportunityDocument(country, asTarget, asSource))
  }
  return results
}
