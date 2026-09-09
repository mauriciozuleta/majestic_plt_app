// Accounting-recognition classification for Commercial Operations entries.
// This is pure data capture for now — the actual accounting/simulation
// engine that reads `accounting_treatment` / `settlement_date` gets wired up
// later. Each category's treatments are mutually exclusive (one entry is one
// kind of event); the revenue-only flags (recurring / discount) are
// independent toggles on top of whichever treatment is picked.

export const REVENUE_TREATMENTS = [
  {
    key: 'earned',
    label: 'Earned Revenue (Cash Sale)',
    description: 'Customer pays at the moment of service.',
  },
  {
    key: 'accrued',
    label: 'Accrued Revenue (Credit Sale)',
    description: 'You deliver now, customer pays later — creates Accounts Receivable.',
    settlementLabel: 'Expected payment date',
  },
  {
    key: 'deferred',
    label: 'Deferred Revenue (Prepaid)',
    description: 'Customer pays now, service later — creates Unearned Revenue (liability).',
    settlementLabel: 'Service delivery date',
  },
]

export const REVENUE_FLAGS = [
  {
    key: 'is_recurring',
    label: 'Recurring Revenue',
    description: 'Subscriptions, memberships, monthly passes.',
  },
  {
    key: 'is_discount',
    label: 'Discount / Promotion',
    description: 'Negative revenue (e.g., early-payment discount).',
  },
]

export const COS_TREATMENTS = [
  {
    key: 'purchase_accrued',
    label: 'Inventory Purchase (Accrued)',
    description: 'You buy goods now, pay later — creates Accounts Payable.',
    settlementLabel: 'Expected payment date',
  },
  {
    key: 'purchase_prepaid',
    label: 'Inventory Purchase (Prepaid)',
    description: 'You pay now, receive goods later — creates Prepaid Inventory (asset).',
    settlementLabel: 'Expected delivery date',
  },
  {
    key: 'consumption',
    label: 'Inventory Consumption',
    description: 'When goods are sold — moves from Inventory to COGS.',
  },
  {
    key: 'direct_production',
    label: 'Direct Production Cost',
    description: 'Fuel, crew, maintenance directly tied to revenue.',
  },
]

export const EXPENSE_TREATMENTS = [
  {
    key: 'cash',
    label: 'Operating Expense (Cash)',
    description: 'Paid immediately.',
  },
  {
    key: 'accrued',
    label: 'Operating Expense (Accrued)',
    description: 'Incurred now, paid later — creates Accounts Payable.',
    settlementLabel: 'Expected payment date',
  },
  {
    key: 'prepaid',
    label: 'Prepaid Expense',
    description: 'Pay now, use later (insurance, annual software).',
    settlementLabel: 'Usage start date',
  },
  {
    key: 'capex',
    label: 'Capital Expense (CAPEX)',
    description: 'Aircraft, equipment, servers — becomes an asset, depreciated.',
  },
  {
    key: 'payroll',
    label: 'Payroll Expense',
    description: 'Often accrued — payroll payable.',
    settlementLabel: 'Payroll payment date',
  },
  {
    key: 'tax',
    label: 'Tax Expense',
    description: 'Often accrued — tax payable.',
    settlementLabel: 'Tax payment date',
  },
]

export function getTreatmentsForCategory(category) {
  if (category === 'revenue') return REVENUE_TREATMENTS
  if (category === 'cos') return COS_TREATMENTS
  if (category === 'expenses') return EXPENSE_TREATMENTS
  return []
}
