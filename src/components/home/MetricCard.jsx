import './MetricCard.css'

function MetricCard({ label, value, tone = 'neutral' }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span className="metric-card__label">{label}</span>
      <strong className="metric-card__value">{value}</strong>
    </div>
  )
}

export default MetricCard
