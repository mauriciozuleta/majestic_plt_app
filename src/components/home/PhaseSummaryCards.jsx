import { useEffect, useMemo, useState } from 'react'
import { fetchSettings } from '../../services/settings'
import { formatCalendarDateCompact } from '../../services/calendarDates'
import { useStartupInvestmentTotals } from '../../hooks/useStartupInvestmentTotals'
import { formatCurrencyValue } from '../../utils/currencyFormat'
import './PhaseSummaryCards.css'

function formatUsdWhole(value) {
  return formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function initialsFor(name) {
  return name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

function logoStyle(company) {
  return company.logo
    ? {
        backgroundImage: `url(${company.logo})`,
        backgroundSize: 'contain',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        backgroundColor: 'var(--bg-card)',
      }
    : { background: `linear-gradient(135deg, ${company.accentFrom}, ${company.accentTo})` }
}

// Companies with no phase assigned yet fall back to Phase 1, mirroring the
// "by default all must be in phase 1" convention set on the company form.
function effectivePhase(company) {
  return company.phaseNumber || 1
}

function PhaseSummaryCards({ companies }) {
  const [settings, setSettings] = useState(null)
  const { totalsByCompanyId, loading: totalsLoading } = useStartupInvestmentTotals(companies)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((data) => {
        if (!cancelled) setSettings(data)
      })
      .catch(() => {
        // Home page degrades to just not showing phase cards — the rest of
        // the page doesn't depend on this fetch succeeding.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const phaseGroups = useMemo(() => {
    if (!settings?.phases_enabled) return []

    const byPhase = new Map()
    companies.forEach((company) => {
      const phaseNumber = effectivePhase(company)
      if (!byPhase.has(phaseNumber)) byPhase.set(phaseNumber, [])
      byPhase.get(phaseNumber).push(company)
    })

    return Array.from(byPhase.entries())
      .sort(([a], [b]) => a - b)
      .map(([phaseNumber, phaseCompanies]) => ({
        phaseNumber,
        companies: phaseCompanies,
        startDate: (settings.phases || []).find((phase) => phase.phase_number === phaseNumber)?.start_date || null,
      }))
  }, [settings, companies])

  if (!settings?.phases_enabled || phaseGroups.length === 0) return null

  return (
    <div className="phase-summary-cards">
      {phaseGroups.map((group) => {
        const groupTotal = group.companies.reduce((sum, company) => sum + (totalsByCompanyId[company.id] || 0), 0)
        return (
          <div className="phase-summary-cards__card" key={group.phaseNumber}>
            <div className="phase-summary-cards__header">
              <span className="phase-summary-cards__title">Phase {group.phaseNumber}</span>
              {group.startDate && (
                <span className="phase-summary-cards__date">
                  {formatCalendarDateCompact(group.startDate, settings.calendar_mode)}
                </span>
              )}
            </div>

            <ul className="phase-summary-cards__companies">
              {group.companies.map((company) => (
                <li key={company.id}>
                  <span className="phase-summary-cards__company-logo" style={logoStyle(company)}>
                    {!company.logo && initialsFor(company.name)}
                  </span>
                  <span className="phase-summary-cards__company-name" style={{ color: company.accentFrom }}>
                    {company.name}
                  </span>
                </li>
              ))}
            </ul>

            <div className="phase-summary-cards__total">
              <span>Start-up investment</span>
              <strong>{totalsLoading ? '…' : formatUsdWhole(groupTotal)}</strong>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default PhaseSummaryCards
