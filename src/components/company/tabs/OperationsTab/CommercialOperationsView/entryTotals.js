import { CATEGORIES } from './categories'

/** Sums a list of entries per category, e.g. for a single day, month, or year. */
export function sumByCategory(entries) {
  return CATEGORIES.map((category) => ({
    ...category,
    total: entries.filter((entry) => entry.category === category.key).reduce((sum, entry) => sum + entry.amount, 0),
  }))
}

/** Entries whose date falls within [start, endExclusive) — plain ISO string
 * comparison, which sorts correctly since every date here is YYYY-MM-DD. */
export function entriesInRange(entries, start, endExclusive) {
  return entries.filter((entry) => entry.entry_date >= start && entry.entry_date < endExclusive)
}

export function formatCategoryTooltip(entries) {
  return sumByCategory(entries)
    .map((category) => `${category.label}: $${category.total.toLocaleString()}`)
    .join('\n')
}
