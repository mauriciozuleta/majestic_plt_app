import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import { fetchPayroll } from '../../../../services/payroll'
import { fetchSettings } from '../../../../services/settings'
import { usePayrollCurrencyRates } from '../../../../hooks/usePayrollCurrencyRates'
import { computeAnnualBreakdown } from '../ManagementTab/PayrollView/payrollDisbursement'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import './OverviewTab.css'

function formatUsdWhole(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// The company's front page — quick-glance stat cards pulled from whichever
// modules already compute them, rather than a second copy of that math.
// Headcount/payroll figures mirror the Payroll tab's own top stat tiles
// (same formula, same Year 1 scope) so the two never disagree.
function OverviewTab() {
  const { companyId } = useParams()
  const company = useAppStore((state) => state.companies.find((item) => item.id === companyId))
  const [rows, setRows] = useState([])
  const [enabledBenefitKeys, setEnabledBenefitKeys] = useState([])
  const [colombiaSmmlvCop, setColombiaSmmlvCop] = useState(undefined)
  const [colombiaUvtCop, setColombiaUvtCop] = useState(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const currencyRates = usePayrollCurrencyRates()

  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    Promise.all([fetchPayroll(companyId, 1), fetchSettings()])
      .then(([nextRows, settings]) => {
        if (cancelled) return
        setRows(nextRows)
        setEnabledBenefitKeys(Array.isArray(settings.enabled_benefits) ? settings.enabled_benefits : [])
        if (settings.colombia_smmlv_cop) setColombiaSmmlvCop(settings.colombia_smmlv_cop)
        if (settings.colombia_uvt_cop) setColombiaUvtCop(settings.colombia_uvt_cop)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [companyId])

  const benefitsContext = useMemo(
    () => ({
      enabledBenefitKeys,
      checksPerYear: 12,
      colombiaRates: { copPerUsd: currencyRates.copPerUsd, smmlvCop: colombiaSmmlvCop, uvtCop: colombiaUvtCop },
      angPerUsd: currencyRates.angPerUsd,
      companyCountryCode: company?.countryCode,
    }),
    [enabledBenefitKeys, currencyRates.copPerUsd, currencyRates.angPerUsd, colombiaSmmlvCop, colombiaUvtCop, company?.countryCode],
  )

  const stats = useMemo(() => {
    const totals = rows.reduce(
      (acc, row) => {
        const headcount = row.headcount ?? 1
        const benefitsAnnual =
          enabledBenefitKeys.length > 0 ? computeAnnualBreakdown(row, benefitsContext).employerBenefitsTotalAnnual * headcount : 0
        return {
          headcount: acc.headcount + headcount,
          monthly: acc.monthly + Number(row.monthly_salary || 0),
          year: acc.year + Number(row.year_salary || 0) * headcount,
          benefits: acc.benefits + benefitsAnnual,
        }
      },
      { headcount: 0, monthly: 0, year: 0, benefits: 0 },
    )
    return { ...totals, positionCount: rows.length }
  }, [rows, enabledBenefitKeys, benefitsContext])

  if (!company) return null

  return (
    <div className="panel-surface overview-tab">
      <h3>{company.name} — Overview</h3>
      <p className="overview-tab__hint">A quick-glance snapshot, pulled from the modules already tracking this data.</p>

      {loading && <div className="overview-tab__status">Loading overview...</div>}
      {error && <div className="overview-tab__status overview-tab__status--error">{error}</div>}

      {!loading && !error && (
        <>
          <h4 className="overview-tab__section-title">Headcount &amp; Payroll</h4>
          <div className="overview-tab__stats">
            <div className="overview-tab__stat-tile">
              <div className="overview-tab__stat-label">Employees</div>
              <div className="overview-tab__stat-value">{stats.headcount.toLocaleString('en-US')}</div>
              <div className="overview-tab__stat-sub">
                {stats.positionCount} position{stats.positionCount === 1 ? '' : 's'}
              </div>
            </div>
            <div className="overview-tab__stat-tile">
              <div className="overview-tab__stat-label">Monthly payroll run-rate</div>
              <div className="overview-tab__stat-value">{formatUsdWhole(stats.monthly)}</div>
              <div className="overview-tab__stat-sub">at current headcount</div>
            </div>
            <div className="overview-tab__stat-tile">
              <div className="overview-tab__stat-label">Year 1 total payroll cost</div>
              <div className="overview-tab__stat-value">{formatUsdWhole(stats.year)}</div>
              <div className="overview-tab__stat-sub">comp × headcount, summed</div>
            </div>
            {enabledBenefitKeys.length > 0 && (
              <div className="overview-tab__stat-tile">
                <div className="overview-tab__stat-label">Employer benefits contributions</div>
                <div className="overview-tab__stat-value">{formatUsdWhole(stats.benefits)}</div>
                <div className="overview-tab__stat-sub">Year 1, at current headcount</div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default OverviewTab
