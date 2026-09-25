import './MetricCard.css'

// `sub` is an optional second line under the value (e.g. a category count)
// — omitted entirely by every caller that doesn't pass one, so this stays
// backward-compatible with the plain label+value card.
function MetricCard({ label, value, tone = 'neutral', sub }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span className="metric-card__label">{label}</span>
      <strong className="metric-card__value">{value}</strong>
      {sub && <span className="metric-card__sub">{sub}</span>}
    </div>
  )
}

export default MetricCard
