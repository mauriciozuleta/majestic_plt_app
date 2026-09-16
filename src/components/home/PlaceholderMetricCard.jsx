import { useMemo } from 'react'
import './pieChart3d.css'
import './PlaceholderMetricCard.css'

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

// No real ROI/valuation computation exists in the app yet, so this draws an
// even split across companies purely to show the intended layout — it must
// never be mistaken for an actual per-company breakdown, hence the muted
// pie, the "Coming soon" badge, and the explicit note below the chart.
function buildEqualConicGradient(companies) {
  if (companies.length === 0) return 'none'
  const share = 100 / companies.length
  let cursor = 0
  const stops = companies.map((company) => {
    const start = cursor
    cursor += share
    return `${company.accentFrom} ${start}% ${cursor}%`
  })
  return `conic-gradient(${stops.join(', ')})`
}

function PlaceholderMetricCard({ label, companies }) {
  const gradient = useMemo(() => buildEqualConicGradient(companies), [companies])

  return (
    <div className="placeholder-metric-card">
      <div className="placeholder-metric-card__header">
        <span className="placeholder-metric-card__label">{label}</span>
        <span className="placeholder-metric-card__badge">Coming soon</span>
      </div>

      {companies.length === 0 ? (
        <div className="placeholder-metric-card__empty">No companies yet.</div>
      ) : (
        <div className="placeholder-metric-card__body">
          <ul className="placeholder-metric-card__breakdown">
            {companies.map((company) => (
              <li key={company.id}>
                <span className="placeholder-metric-card__company-logo" style={logoStyle(company)}>
                  {!company.logo && initialsFor(company.name)}
                </span>
                <span className="placeholder-metric-card__company-name" style={{ color: company.accentFrom }}>
                  {company.name}
                </span>
                <span className="placeholder-metric-card__company-amount">—</span>
              </li>
            ))}
          </ul>

          <div className="placeholder-metric-card__pie-section">
            <div className="pie-chart-3d-wrap">
              <div
                className="pie-chart-3d pie-chart-3d--muted"
                style={{ background: gradient }}
                role="img"
                aria-label={`Placeholder even split — ${label} figures are not yet available`}
              />
            </div>
            <p className="placeholder-metric-card__note">
              Even split shown as a placeholder. Real per-company {label.toLowerCase()} will replace this once that
              calculation is built.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default PlaceholderMetricCard
