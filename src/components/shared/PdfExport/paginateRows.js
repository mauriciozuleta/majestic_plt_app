const LETTERHEAD_PX = 100
const SUBHEAD_PX = 30
const SUMMARY_PX = 90
const SIGNOFF_FOOTER_PX = 120
const CAT_ROW_WEIGHT = 1.25
const GRAND_ROW_WEIGHT = 1.3

function flattenRows(sections, totalsRow) {
  const flat = []
  sections.forEach((section) => {
    flat.push({ kind: 'cat', section })
    section.records.forEach((record) => flat.push({ kind: 'record', section, record }))
    flat.push({ kind: 'subtotal', section })
  })
  if (totalsRow) flat.push({ kind: 'grand', totalsRow })
  return flat
}

function rowWeight(kind) {
  if (kind === 'cat') return CAT_ROW_WEIGHT
  if (kind === 'grand') return GRAND_ROW_WEIGHT
  return 1
}

// Chunks the ledger's rows into physical pages, given the actual pixel
// budget each page has once the letterhead/summary/thead/signoff blocks are
// accounted for. This replaces relying on the browser's print engine to
// auto-paginate overflowing content (which this app's target environment
// does not reliably do) with an explicit, computed page break.
export function paginateRows({ sections, totalsRow, hasSummaryTiles, rowHeightPx, contentAreaHeightPx }) {
  const flat = flattenRows(sections, totalsRow)
  const theadPx = rowHeightPx * 1.3

  const firstBudget = contentAreaHeightPx - LETTERHEAD_PX - SUBHEAD_PX - (hasSummaryTiles ? SUMMARY_PX : 0) - theadPx - SIGNOFF_FOOTER_PX
  const continuationBudget = contentAreaHeightPx - LETTERHEAD_PX - SUBHEAD_PX - theadPx - SIGNOFF_FOOTER_PX

  const pages = []
  let current = []
  let used = 0
  let pageIndex = 0

  const budgetFor = (index) => (index === 0 ? firstBudget : continuationBudget)

  for (let i = 0; i < flat.length; i += 1) {
    const row = flat[i]
    const h = rowWeight(row.kind) * rowHeightPx
    const budget = budgetFor(pageIndex)

    const isCatRow = row.kind === 'cat'
    const nextH = i + 1 < flat.length ? rowWeight(flat[i + 1].kind) * rowHeightPx : 0
    const wouldOverflow = used + h > budget
    const catWouldBeOrphaned = isCatRow && used + h + nextH > budget

    if ((wouldOverflow || catWouldBeOrphaned) && current.length > 0) {
      pages.push(current)
      current = []
      used = 0
      pageIndex += 1
    }

    current.push(row)
    used += h
  }
  if (current.length > 0) pages.push(current)
  if (pages.length === 0) pages.push([])
  return pages
}
