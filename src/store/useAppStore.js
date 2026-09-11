import { create } from 'zustand'

const ACTIVE_COMPANY_KEY = 'majestic-active-company-id'
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
      const nextActiveCompanyId =
        companies.find((company) => company.id === state.activeCompanyId)?.id ??
        companies[0]?.id ??
        null

      persistActiveCompanyId(nextActiveCompanyId)

      return {
        companies,
        activeCompanyId: nextActiveCompanyId,
      }
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
