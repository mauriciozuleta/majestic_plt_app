import { useEffect, useState } from 'react'
import { fetchStartupInvestmentPlan, fetchStartupInvestmentRecords } from '../services/startupInvestment'
import { EXPENSE_CATEGORY_KEYS, WORKING_CAPITAL_KEY } from '../components/company/tabs/FinancialTab/startupInvestmentPdfSpec'

// Shared by every Home-page card that needs per-company start-up investment
// totals (the category breakdown card and the phase cards) so there's one
// fetch per company, not one per card.
export function useStartupInvestmentTotals(companies) {
  const [totalsByCompanyId, setTotalsByCompanyId] = useState({})
  const [totalsByCategory, setTotalsByCategory] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (companies.length === 0) {
      setTotalsByCompanyId({})
      setTotalsByCategory({})
      setLoading(false)
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError('')

    Promise.all(
      companies.map(async (company) => {
        const plan = await fetchStartupInvestmentPlan(company.id)
        // No plan yet for this company (fetchStartupInvestmentPlan returns
        // null on 404) — records would 404 too, so it contributes $0 rather
        // than being skipped out of the breakdown entirely.
        if (!plan) return [company.id, []]

        const records = await fetchStartupInvestmentRecords(company.id)
        return [company.id, records]
      }),
    )
      .then((pairs) => {
        if (cancelled) return

        const nextTotalsByCompanyId = {}
        const nextTotalsByCategory = {}

        pairs.forEach(([companyId, records]) => {
          let companyTotal = 0
          records.forEach((record) => {
            const countsTowardTotal = EXPENSE_CATEGORY_KEYS.includes(record.category) || record.category === WORKING_CAPITAL_KEY
            if (!countsTowardTotal) return
            companyTotal += record.total_amount
            nextTotalsByCategory[record.category] = (nextTotalsByCategory[record.category] || 0) + record.total_amount
          })
          nextTotalsByCompanyId[companyId] = companyTotal
        })

        setTotalsByCompanyId(nextTotalsByCompanyId)
        setTotalsByCategory(nextTotalsByCategory)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load start-up investment totals.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [companies])

  return { totalsByCompanyId, totalsByCategory, loading, error }
}
