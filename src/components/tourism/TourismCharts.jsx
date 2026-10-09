// Small SVG charts (the project has no chart library; none is added for this module).

const PALETTE = ['#14b8a6', '#60a5fa', '#f59e0b', '#c084fc', '#f87171', '#34d399', '#fb923c', '#a3e635']

export function BarChart({ title, items, format, color = '#14b8a6' }) {
  const rows = items.filter((item) => item.value != null).sort((a, b) => b.value - a.value)
  const max = Math.max(...rows.map((row) => row.value), 0)
  const rowHeight = 22
  const labelWidth = 130
  const valueWidth = 96
  const width = 520
  const height = Math.max(rows.length, 1) * rowHeight + 8
  return (
    <figure className="tourism__chart">
      <figcaption>{title}</figcaption>
      {rows.length === 0 ? (
        <p className="tourism__muted">No data for the selected countries.</p>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          {rows.map((row, index) => {
            const barWidth = max > 0 ? ((width - labelWidth - valueWidth) * row.value) / max : 0
            const y = index * rowHeight + 4
            return (
              <g key={row.label}>
                <text x={labelWidth - 6} y={y + 14} textAnchor="end" className="tourism__chart-label">
                  {row.label.length > 18 ? `${row.label.slice(0, 17)}…` : row.label}
                </text>
                <rect x={labelWidth} y={y + 2} width={Math.max(barWidth, 1)} height={rowHeight - 8} rx="3" fill={color} />
                <text x={labelWidth + barWidth + 6} y={y + 14} className="tourism__chart-value">
                  {format(row.value)}
                  {row.year ? ` (${row.year})` : ''}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </figure>
  )
}

export function LineChart({ title, series, format }) {
  const lines = series.filter((line) => line.points.length > 0)
  const years = lines.flatMap((line) => line.points.map((point) => point.year))
  const values = lines.flatMap((line) => line.points.map((point) => point.value))
  const width = 520
  const height = 240
  const pad = { left: 52, right: 12, top: 12, bottom: 28 }
  if (lines.length === 0) {
    return (
      <figure className="tourism__chart">
        <figcaption>{title}</figcaption>
        <p className="tourism__muted">No historical data for the selected countries.</p>
      </figure>
    )
  }
  const minYear = Math.min(...years)
  const maxYear = Math.max(...years)
  const maxValue = Math.max(...values, 0)
  const x = (year) => pad.left + (maxYear === minYear ? 0.5 : (year - minYear) / (maxYear - minYear)) * (width - pad.left - pad.right)
  const y = (value) => pad.top + (1 - (maxValue > 0 ? value / maxValue : 0)) * (height - pad.top - pad.bottom)
  const ticks = [0, 0.5, 1].map((fraction) => maxValue * fraction)
  return (
    <figure className="tourism__chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className="tourism__chart-grid" />
            <text x={pad.left - 6} y={y(tick) + 4} textAnchor="end" className="tourism__chart-label">
              {format(tick)}
            </text>
          </g>
        ))}
        <text x={pad.left} y={height - 8} className="tourism__chart-label">
          {minYear}
        </text>
        <text x={width - pad.right} y={height - 8} textAnchor="end" className="tourism__chart-label">
          {maxYear}
        </text>
        {lines.map((line, index) => {
          const color = PALETTE[index % PALETTE.length]
          const sorted = [...line.points].sort((a, b) => a.year - b.year)
          return (
            <g key={line.label}>
              <polyline fill="none" stroke={color} strokeWidth="2" points={sorted.map((point) => `${x(point.year)},${y(point.value)}`).join(' ')} />
              {sorted.map((point) => (
                <circle key={point.year} cx={x(point.year)} cy={y(point.value)} r="2.5" fill={color}>
                  <title>{`${line.label} ${point.year}: ${format(point.value)}`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <div className="tourism__legend">
        {lines.map((line, index) => (
          <span key={line.label}>
            <i style={{ background: PALETTE[index % PALETTE.length] }} />
            {line.label}
          </span>
        ))}
      </div>
    </figure>
  )
}
