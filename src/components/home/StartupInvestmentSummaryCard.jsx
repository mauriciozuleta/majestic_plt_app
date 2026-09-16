import { useMemo } from 'react'
import { useAppStore } from '../../store/useAppStore'
import { useStartupInvestmentTotals } from '../../hooks/useStartupInvestmentTotals'
import { CATEGORIES } from '../company/tabs/FinancialTab/startupInvestmentPdfSpec'
import { formatCurrencyValue } from '../../utils/currencyFormat'
import './pieChart3d.css'
import './StartupInvestmentSummaryCard.css'

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

// One conic-gradient stop per category, in one pass — no charting library
// needed for a single static-ish pie like this.
function buildConicGradient(segments) {
  let cursor = 0
  const stops = segments.map(({ color, percent }) => {
    const start = cursor
    cursor += percent
    return `${color} ${start}% ${cursor}%`
  })
  return `conic-gradient(${stops.join(', ')})`
}

function StartupInvestmentSummaryCard() {
  const companies = useAppStore((state) => state.companies)
  const { totalsByCompanyId, totalsByCategory, loading, error } = useStartupInvestmentTotals(companies)

  const grandTotal = useMemo(
    () => Object.values(totalsByCompanyId).reduce((sum, value) => sum + value, 0),
    [totalsByCompanyId],
  )

  // Recomputed from totalsByCategory/grandTotal on every render they change
  // — so a newly-added record (once the fetch above picks it up) or a newly
  // added company immediately shifts every slice's share, not just its own.
  const pieSegments = useMemo(() => {
    if (grandTotal <= 0) return []
    return CATEGORIES.map((category) => ({
      key: category.key,
      label: category.label,
      color: category.color,
      amount: totalsByCategory[category.key] || 0,
      percent: ((totalsByCategory[category.key] || 0) / grandTotal) * 100,
    })).filter((segment) => segment.amount > 0)
  }, [totalsByCategory, grandTotal])

  return (
    <div className="startup-investment-summary-card">
      <div className="startup-investment-summary-card__header">
        <span className="startup-investment-summary-card__label">Total Start-up Investment</span>
        <strong className="startup-investment-summary-card__total">{loading ? '…' : formatUsdWhole(grandTotal)}</strong>
      </div>

      {error ? (
        <div className="startup-investment-summary-card__error">{error}</div>
      ) : companies.length === 0 ? (
        <div className="startup-investment-summary-card__empty">No companies yet.</div>
      ) : (
        <div className="startup-investment-summary-card__body">
          <ul className="startup-investment-summary-card__breakdown">
            {companies.map((company) => (
              <li key={company.id}>
                <span className="startup-investment-summary-card__company-logo" style={logoStyle(company)}>
                  {!company.logo && initialsFor(company.name)}
                </span>
                <span className="startup-investment-summary-card__company-name" style={{ color: company.accentFrom }}>
                  {company.name}
                </span>
                <span className="startup-investment-summary-card__company-amount">
                  {loading ? '…' : formatUsdWhole(totalsByCompanyId[company.id] ?? 0)}
                </span>
              </li>
            ))}
          </ul>

          {pieSegments.length > 0 && (
            <div className="startup-investment-summary-card__pie-section">
              <div className="pie-chart-3d-wrap">
                <div
                  className="pie-chart-3d"
                  style={{ background: buildConicGradient(pieSegments) }}
                  role="img"
                  aria-label="Share of start-up investment by category"
                />
              </div>
              <ul className="startup-investment-summary-card__legend">
                {pieSegments.map((segment) => (
                  <li key={segment.key}>
                    <span className="startup-investment-summary-card__legend-swatch" style={{ background: segment.color }} />
                    <span className="startup-investment-summary-card__legend-label">{segment.label}</span>
                    <span className="startup-investment-summary-card__legend-percent">{segment.percent.toFixed(1)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default StartupInvestmentSummaryCard
