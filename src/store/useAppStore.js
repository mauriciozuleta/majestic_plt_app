import { create } from 'zustand'

const ACTIVE_COMPANY_KEY = 'majestic-active-company-id'
const COMPANY_ORDER_KEY = 'majestic-company-order'
const LEGACY_STORAGE_KEY = 'majestic-app-state'

const loadPersistedActiveCompanyId = () => {
  if (typeof window === 'undefined') return null

  try {
    const activeCompanyId = window.localStorage.getItem(ACTIVE_COMPANY_KEY)
    if (activeCompanyId) return activeCompanyId

    const legacyState = window.localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!legacyState) return null

    const parsed = JSON.parse(legacyState)
    return parsed?.activeCompanyId ?? null
  } catch {
    return null
  }
}

const persistActiveCompanyId = (activeCompanyId) => {
  if (typeof window === 'undefined') return

  if (activeCompanyId) {
    window.localStorage.setItem(ACTIVE_COMPANY_KEY, activeCompanyId)
  } else {
    window.localStorage.removeItem(ACTIVE_COMPANY_KEY)
  }
}

const loadPersistedCompanyOrder = () => {
  if (typeof window === 'undefined') return []

  try {
    const raw = window.localStorage.getItem(COMPANY_ORDER_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const persistCompanyOrder = (companyIds) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(COMPANY_ORDER_KEY, JSON.stringify(companyIds))
}

// Sidebar drag-to-reorder is purely a per-browser display preference (see
// CompanyList.jsx) — not synced to the backend, same scope as
// ACTIVE_COMPANY_KEY above. Companies not yet in the saved order (new ones,
// or a first run with no saved order at all) keep their fetch order,
// appended after every company the saved order does know about.
const applyPersistedCompanyOrder = (companies) => {
  const order = loadPersistedCompanyOrder()
  if (order.length === 0) return companies

  const byId = new Map(companies.map((company) => [company.id, company]))
  const ordered = order.map((id) => byId.get(id)).filter(Boolean)
  const orderedIds = new Set(ordered.map((company) => company.id))
  const remaining = companies.filter((company) => !orderedIds.has(company.id))
  return [...ordered, ...remaining]
}

const initialActiveCompanyId = loadPersistedActiveCompanyId()

export const useAppStore = create((set, get) => ({
  companies: [],
  activeCompanyId: initialActiveCompanyId,
  currentUser: null,
  sidebarOpen: false,
  assistantMessages: [],

  setCurrentUser: (user) => set({ currentUser: user }),
  setCompanies: (companies) =>
    set((state) => {
      const orderedCompanies = applyPersistedCompanyOrder(companies)
      const nextActiveCompanyId =
        orderedCompanies.find((company) => company.id === state.activeCompanyId)?.id ??
        orderedCompanies[0]?.id ??
        null

      persistActiveCompanyId(nextActiveCompanyId)

      return {
        companies: orderedCompanies,
        activeCompanyId: nextActiveCompanyId,
      }
    }),
  reorderCompanies: (draggedCompanyId, targetCompanyId) =>
    set((state) => {
      if (draggedCompanyId === targetCompanyId) return {}

      const companies = [...state.companies]
      const fromIndex = companies.findIndex((company) => company.id === draggedCompanyId)
      const toIndex = companies.findIndex((company) => company.id === targetCompanyId)
      if (fromIndex === -1 || toIndex === -1) return {}

      const [dragged] = companies.splice(fromIndex, 1)
      companies.splice(toIndex, 0, dragged)

      persistCompanyOrder(companies.map((company) => company.id))
      return { companies }
    }),
  addCompany: (company) => {
    set((state) => ({
      companies: (() => {
        const nextCompanies = [...state.companies, company]
        persistActiveCompanyId(company.id)
        return nextCompanies
      })(),
      activeCompanyId: company.id,
    }))
  },
  updateCompany: (company) =>
    set((state) => ({
      companies: state.companies.map((existing) => (existing.id === company.id ? company : existing)),
    })),
  removeCompany: (companyId) =>
    set((state) => {
      const companies = state.companies.filter((company) => company.id !== companyId)
      const nextActiveCompanyId =
        state.activeCompanyId === companyId
          ? companies[0]?.id ?? null
          : state.activeCompanyId

      persistActiveCompanyId(nextActiveCompanyId)

      return {
        companies,
        activeCompanyId: nextActiveCompanyId,
      }
    }),
  setActiveCompanyId: (companyId) =>
    set((state) => {
      persistActiveCompanyId(companyId)
      return { activeCompanyId: companyId }
    }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  getActiveCompany: () => {
    const { companies, activeCompanyId } = get()
    return companies.find((company) => company.id === activeCompanyId) ?? null
  },
  // Pushed from background-job polling (see services/backgroundJobs.js), not
  // just from a mounted component — a long-running build (country profile,
  // competitiveness analysis) keeps polling after the triggering panel is
  // navigated away from, and posts its result here when done, since this
  // store — unlike component state — survives that navigation.
  addAssistantMessage: (text) =>
    set((state) => ({
      assistantMessages: [...state.assistantMessages, { id: Date.now() + Math.random(), sender: 'bot', text }],
    })),
}))
