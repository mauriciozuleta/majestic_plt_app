// Shared with DocumentationTab's Start-up Investment link, so both places
// generate the exact same PDF from the exact same logic — not a second,
// possibly-drifting copy of this math.

export const CATEGORIES = [
  { key: 'assets_acquisition', label: 'Start-up Assets Acquisition', color: '#35D399' },
  { key: 'other_assets_purchases', label: 'Other assets Purchases', color: '#38bdf8' },
  { key: 'startup_expenses', label: 'Start-up Expenses', color: '#f59e0b' },
  { key: 'startup_payroll', label: 'Start-up development payroll', color: '#a78bfa' },
  { key: 'working_capital', label: 'Start-up Working capital requirement', color: '#f87171' },
]
export const EXPENSE_CATEGORY_KEYS = ['assets_acquisition', 'other_assets_purchases', 'startup_expenses', 'startup_payroll']
export const WORKING_CAPITAL_KEY = 'working_capital'

export function buildStartupInvestmentPdfSpec(plan, records) {
  const monthCount = plan.pre_operational_months
  const recordsByCategory = new Map(CATEGORIES.map((category) => [category.key, []]))
  records.forEach((record) => {
    const list = recordsByCategory.get(record.category)
    if (list) list.push(record)
  })

  const categoryTotals = (key) => (recordsByCategory.get(key) || []).reduce((sum, record) => sum + record.total_amount, 0)

  const categoryMonths = (key) => {
    const totals = new Array(monthCount).fill(0)
    ;(recordsByCategory.get(key) || []).forEach((record) => {
      record.months.forEach((value, index) => {
        totals[index] += value
      })
    })
    return totals
  }

  const totalStartupExpenses = EXPENSE_CATEGORY_KEYS.reduce((sum, key) => sum + categoryTotals(key), 0)
  const totalWorkingCapital = categoryTotals(WORKING_CAPITAL_KEY)
  const totalRequiredInvestment = totalStartupExpenses + totalWorkingCapital

  const monthlyCashRequirement = Array.from({ length: monthCount }, (_, index) =>
    CATEGORIES.reduce((sum, category) => sum + categoryMonths(category.key)[index], 0),
  )

  return {
    documentTitle: 'Start-up Investment Requirement',
    eyebrow: 'Financial Planning',
    periodsCaption: `Pre-operational period: ${monthCount} month${monthCount === 1 ? '' : 's'}`,
    periodLabels: Array.from({ length: monthCount }, (_, index) => `M${index + 1}`),
    summaryTiles: [
      { label: 'Total Start-up Expenses', value: totalStartupExpenses },
      { label: 'Total Start-up Working Capital', value: totalWorkingCapital },
      { label: 'Total Start-up Required Investment', value: totalRequiredInvestment, primary: true },
    ],
    sections: CATEGORIES.map((category) => ({
      key: category.key,
      label: category.label,
      color: category.color,
      records: (recordsByCategory.get(category.key) || []).map((record) => ({
        name: record.name,
        values: record.months,
        total: record.total_amount,
      })),
      subtotal: { values: categoryMonths(category.key), total: categoryTotals(category.key) },
    })),
    totalsRow: {
      label: 'Monthly Cash Requirement',
      values: monthlyCashRequirement,
      total: monthlyCashRequirement.reduce((sum, value) => sum + value, 0),
    },
  }
}
