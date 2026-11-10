// Dependency-free SVG line chart: the price series, optional second line (Brent or crack spread, same USD/gal axis) and vertical event markers.
import { useState } from 'react'
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

function FuelChart({ primary, secondary, secondaryLabel, periodType, events = [] }) {
  const [activeIndex, setActiveIndex] = useState(null)
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
  const active = activeIndex === null ? null : primary?.[activeIndex]
  const activeX = active ? xOf([active])[0] : 0
  const activeY = active ? yOf([active])[0] : 0
  const comparison = active && secondary?.find((point) => point.date === active.date)
  const tooltipX = Math.max(PAD.left, Math.min(activeX + 12, W - 252))
  const tooltipY = Math.max(PAD.top, Math.min(activeY - 78, H - PAD.bottom - 76))
  const dateLabel = active && new Date(`${active.date}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'long', year: 'numeric', ...(periodType === 'month' ? {} : { day: 'numeric' }), timeZone: 'UTC',
  })
  const inspect = (event) => {
    const svg = event.currentTarget
    const matrix = svg.getScreenCTM()
    if (!matrix) return
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    const x = point.matrixTransform(matrix.inverse()).x
    const target = tMin + ((x - PAD.left) / innerW) * (tMax - tMin)
    // Inspect original observations, including points omitted from the drawn path.
    let best = 0
    primary.forEach((p, i) => {
      if (Math.abs(Date.parse(p.date) - target) < Math.abs(Date.parse(primary[best].date) - target)) best = i
    })
    setActiveIndex(best)
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="fuel-chart" role="group" tabIndex={0}
      aria-label="Fuel price chart. Hover or tap for prices. Use left and right arrow keys to inspect observations."
      onPointerMove={inspect} onPointerDown={inspect} onPointerLeave={() => setActiveIndex(null)}
      onFocus={() => setActiveIndex(primary.length - 1)} onBlur={() => setActiveIndex(null)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setActiveIndex(null)
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          event.preventDefault()
          setActiveIndex((index) => Math.max(0, Math.min(primary.length - 1, (index ?? primary.length - 1) + (event.key === 'ArrowLeft' ? -1 : 1))))
        }
      }}>
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
      {active && (
        <g className="fuel-chart__inspection" pointerEvents="none">
          <line x1={activeX} x2={activeX} y1={PAD.top} y2={H - PAD.bottom} className="fuel-chart__cursor" />
          <circle cx={activeX} cy={activeY} r={4} className="fuel-chart__point" />
          <g transform={`translate(${tooltipX}, ${tooltipY})`} role="tooltip" aria-live="polite">
            <rect width={240} height={comparison ? 74 : 54} rx={6} className="fuel-chart__tooltip-bg" />
            <text x={10} y={19} className="fuel-chart__tooltip-text">{dateLabel}</text>
            <text x={10} y={39} className="fuel-chart__tooltip-text">Fuel: ${active.value.toFixed(3)} / US gal</text>
            {comparison && <text x={10} y={59} className="fuel-chart__tooltip-text">{secondaryLabel}: ${comparison.value.toFixed(3)} / US gal</text>}
          </g>
        </g>
      )}
    </svg>
  )
}

export default FuelChart
