// Remembers, per company, the sub-path (everything after /company/:id/) the
// user last visited inside that company's workspace — so leaving a company
// entirely (Home, Settings, another company) and coming back lands back on
// the same tab instead of always resetting to management/roadmap. Per
// browser via localStorage, same scope as the other majestic-* keys in
// useAppStore.js.
const STORAGE_KEY = 'majestic-company-last-path'

function readAll() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

// Sub-paths that used to be real company tabs but no longer are — a value
// saved before such a move must not be replayed as-is (it now 404s, or
// worse, happens to still resolve to something else entirely, as
// operations/market-analysis does now that /market-analysis is the
// standalone module's own route). Add an old path here whenever a company
// tab moves or is removed.
const STALE_PATHS = new Set(['operations/market-analysis'])

export function getLastCompanyPath(companyId) {
  if (!companyId) return null
  const saved = readAll()[companyId] ?? null
  return saved && !STALE_PATHS.has(saved) ? saved : null
}

export function setLastCompanyPath(companyId, subPath) {
  if (typeof window === 'undefined' || !companyId || !subPath) return
  const all = readAll()
  if (all[companyId] === subPath) return
  all[companyId] = subPath
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
}
