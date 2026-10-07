import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// The Tax Calculator's work, kept across tab changes and reloads (localStorage): the export and import countries, the product and its tariff line, the
// price per kg, the last result (always per 1 kg, in USD — see components/taxCalculator/taxResult.js) and a history of the products calculated.

const MAX_HISTORY = 30

export const EMPTY_FORM = { price: '', commercial: false }

export const useTaxCalcStore = create(
  persist(
    (set) => ({
      origin: '', // the exporting country: its product portfolio is the list to choose from
      destination: '', // the importing country (one with its duties and taxes built: Jamaica, Colombia, United States)
      product: null, // the portfolio product chosen: { name, category, hsCode, priceUsdPerKg, source }
      line: null, // the destination tariff line (Jamaica / United States): { code, description, path, units, summary }
      lineNote: '', // how the line was chosen when it was a judgement call
      form: EMPTY_FORM, // price per kg in USD; whether the importer is a registered commercial importer (Jamaica)
      result: null, // the normalized per-kg result
      history: [],
      dianLines: {}, // Colombia: the 10-digit tariff line the user picked for a product (product key -> code), so the choice is remembered
      update: (patch) => set(patch),
      setForm: (patch) => set((state) => ({ form: { ...state.form, ...patch } })),
      rememberDianLine: (key, code) => set((state) => ({ dianLines: { ...state.dianLines, [key]: code } })),
      addHistory: (entry) => set((state) => ({ history: [entry, ...state.history.filter((item) => item.id !== entry.id)].slice(0, MAX_HISTORY) })),
      removeHistory: (id) => set((state) => ({ history: state.history.filter((item) => item.id !== id) })),
      clearHistory: () => set({ history: [] }),
    }),
    {
      name: 'majestic-tax-calculator',
      version: 2, // v1 kept a quantity and a different result shape: only the countries survive
      migrate: (persisted) => ({ origin: persisted?.origin || '', destination: persisted?.destination || '' }),
      partialize: (state) => ({
        origin: state.origin,
        destination: state.destination,
        product: state.product,
        line: state.line,
        lineNote: state.lineNote,
        form: state.form,
        result: state.result,
        history: state.history,
        dianLines: state.dianLines,
      }),
    },
  ),
)
