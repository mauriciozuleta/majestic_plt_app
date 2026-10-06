import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// The Tax Calculator's work, kept across tab changes and reloads (localStorage): the countries chosen, the product and tariff
// line selected, the shipment values, the last result, and a history of the calculations performed.

const MAX_HISTORY = 30

export const EMPTY_FORM = { price: '', quantity: '', units: '', commercial: false }

export const useTaxCalcStore = create(
  persist(
    (set) => ({
      destination: '',
      origin: '',
      query: '',
      product: null, // the portfolio product chosen from the origin's list: { name, category, hsCode, priceUsdPerKg, source }
      line: null, // the destination tariff line: { code, description, path, units, summary }
      lineNote: '', // how the line was chosen when it was a judgement call
      form: EMPTY_FORM,
      result: null,
      history: [],
      update: (patch) => set(patch),
      setForm: (patch) => set((state) => ({ form: { ...state.form, ...patch } })),
      addHistory: (entry) => set((state) => ({ history: [entry, ...state.history.filter((item) => item.id !== entry.id)].slice(0, MAX_HISTORY) })),
      removeHistory: (id) => set((state) => ({ history: state.history.filter((item) => item.id !== id) })),
      clearHistory: () => set({ history: [] }),
    }),
    {
      name: 'majestic-tax-calculator',
      version: 1,
      partialize: (state) => ({
        destination: state.destination,
        origin: state.origin,
        query: state.query,
        product: state.product,
        line: state.line,
        lineNote: state.lineNote,
        form: state.form,
        result: state.result,
        history: state.history,
      }),
    },
  ),
)
