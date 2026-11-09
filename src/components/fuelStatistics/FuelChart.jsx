// Dependency-free SVG line chart: the price series, optional second line (Brent or crack spread, same USD/gal axis) and vertical event markers.
const W = 760
const H = 260
const PAD = { left: 46, right: 12, top: 12, bottom: 24 }

function scale(values, min, max, size, offset, invert = false) {
  const span = max - min || 1
  return values.map((v) => {
    const t = (v - min) / span
    return offset + (invert ? (1 - t) * size : t * size)
  })
}

function path(xs, ys) {
  return xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
}

// Keeps at most ~600 points so a 36-year daily series stays light.
function thin(points) {
  if (points.length <= 600) return points
  const step = Math.ceil(points.length / 600)
  return points.filter((_, i) => i % step === 0 || i === points.length - 1)
}

function FuelChart({ primary, secondary, secondaryLabel, events = [] }) {
  const main = thin(primary || [])
  if (main.length < 2) return <p className="fuel-stats__empty">Not enough points to draw a chart.</p>
  const second = thin(secondary || [])
  const times = (pts) => pts.map((p) => new Date(p.date).getTime())
  const allT = [...times(main), ...times(second)]
  const tMin = Math.min(...allT)
  const tMax = Math.max(...allT)
  const allV = [...main.map((p) => p.value), ...second.map((p) => p.value)]
  const vMin = Math.min(0, ...allV)
  const vMax = Math.max(...allV) * 1.05
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const xOf = (pts) => scale(times(pts), tMin, tMax, innerW, PAD.left)
  const yOf = (pts) => scale(pts.map((p) => p.value), vMin, vMax, innerH, PAD.top, true)
  const ticks = Array.from({ length: 5 }, (_, i) => vMin + ((vMax - vMin) * i) / 4)
  const eventsIn = events.filter((e) => {
    const t = new Date(e.date).getTime()
    return t >= tMin && t <= tMax
  })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="fuel-chart" role="img" aria-label="Fuel price chart">
      {ticks.map((tick) => {
        const y = PAD.top + (1 - (tick - vMin) / (vMax - vMin || 1)) * innerH
        return (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} className="fuel-chart__grid" />
            <text x={PAD.left - 6} y={y + 3} textAnchor="end" className="fuel-chart__label">{tick.toFixed(2)}</text>
          </g>
        )
      })}
      <text x={PAD.left} y={H - 6} className="fuel-chart__label">{main[0].date}</text>
      <text x={W - PAD.right} y={H - 6} textAnchor="end" className="fuel-chart__label">{main[main.length - 1].date}</text>
      {eventsIn.map((e) => {
        const x = PAD.left + ((new Date(e.date).getTime() - tMin) / (tMax - tMin || 1)) * innerW
        return (
          <g key={`${e.date}-${e.title}`}>
            <line x1={x} x2={x} y1={PAD.top} y2={H - PAD.bottom} className="fuel-chart__event" />
            <title>{`${e.date}: ${e.title}`}</title>
          </g>
        )
      })}
      {second.length > 1 && <path d={path(xOf(second), yOf(second))} className="fuel-chart__line fuel-chart__line--second"><title>{secondaryLabel}</title></path>}
      <path d={path(xOf(main), yOf(main))} className="fuel-chart__line" />
    </svg>
  )
}

export default FuelChart
