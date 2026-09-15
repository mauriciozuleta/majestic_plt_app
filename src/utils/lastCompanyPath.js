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

export function getLastCompanyPath(companyId) {
  if (!companyId) return null
  return readAll()[companyId] ?? null
}

export function setLastCompanyPath(companyId, subPath) {
  if (typeof window === 'undefined' || !companyId || !subPath) return
  const all = readAll()
  if (all[companyId] === subPath) return
  all[companyId] = subPath
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
}
