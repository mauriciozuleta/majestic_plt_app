import { Component, Suspense, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Line } from '@react-three/drei'
import { colors, fmt } from './format'

class ViewBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <p>3D is unavailable in this browser. Use the cross-section below.</p> : this.props.children }
}

function Scene({ position: p, selected, onSelect }) {
  const points = p.contour.points
  const width = Math.max(...points.map(pt => pt[1]))
  const shape = points.map(([z, w]) => [-w / 2, z]).concat([...points].reverse().map(([z, w]) => [w / 2, z]))
  shape.push(shape[0])
  return <>
    <ambientLight intensity={1.7} /><directionalLight position={[200, 400, 100]} intensity={2} />
    <mesh position={[0, -2, 0]}><boxGeometry args={[width, 4, p.length]} /><meshStandardMaterial color="#28323d" /></mesh>
    {[-p.length / 2, p.length / 2].map(y => <Line key={y} points={shape.map(([x, z]) => [x, z, y])} color="#a5b5c4" lineWidth={1} />)}
    {points.flatMap(([z, w], i) => [-1, 1].map(side => <Line key={`${i}-${side}`} points={[[side * w / 2, z, -p.length / 2], [side * w / 2, z, p.length / 2]]} color="#526374" />))}
    <Line points={[[-width / 2, 2, -p.length / 2], [width / 2, 2, -p.length / 2]]} color="#f87171" lineWidth={4} />
    {p.boxes.map(b => <mesh key={b.box_id} position={[b.x + b.dx / 2, b.z + b.dz / 2, b.y + b.dy / 2]} onClick={e => { e.stopPropagation(); onSelect(selected === b.box_id ? null : b.box_id) }}>
      <boxGeometry args={[b.dx - .5, b.dz - .5, b.dy - .5]} /><meshStandardMaterial color={colors[b.type_index % colors.length]} transparent opacity={!selected || selected === b.box_id ? .95 : .13} /></mesh>)}
    <OrbitControls makeDefault target={[0, points.at(-1)[0] / 2, 0]} minDistance={100} maxDistance={1600} />
  </>
}

export function CrossSection({ position: p, clearance = 0 }) {
  const width = Math.max(...p.contour.points.map(pt => pt[1]))
  const height = p.contour.points.at(-1)[0]
  const outline = c => p.contour.points.map(([z, w]) => `${-w / 2 + c},${-z}`).concat([...p.contour.points].reverse().map(([z, w]) => `${w / 2 - c},${-z}`)).join(' ')
  return <svg className="packer-section-svg" viewBox={`${-width / 2 - 15} ${-height - 15} ${width + 30} ${height + 35}`} role="img" aria-label="Cross-section looking forward; aircraft geometry is an estimate">
    <polygon points={outline(0)} fill="none" stroke="var(--text-muted)" strokeWidth="1.5" />
    <polygon points={outline(clearance)} fill="none" stroke="var(--accent-amber)" strokeDasharray="4 3" />
    {p.boxes.map(b => <rect key={b.box_id} x={b.x} y={-b.z - b.dz} width={b.dx} height={b.dz} fill={colors[b.type_index % colors.length]} fillOpacity=".12" stroke={colors[b.type_index % colors.length]} strokeWidth=".6"><title>{b.box_id} · {b.box_type}{b.leans ? ' · wall-supported' : ''}</title></rect>)}
    <text x="0" y="14" textAnchor="middle" fill="var(--text-muted)" fontSize="8">Looking forward · cm · geometry estimate</text>
  </svg>
}

export default function PositionView({ position, clearance }) {
  const [selected, setSelected] = useState(null)
  const box = position.boxes.find(b => b.box_id === selected)
  return <section className="packer-card"><div className="packer-section-head"><h3>{position.position} · Build preview</h3><span>Drag to orbit · Scroll to zoom · Select a box</span></div>
    <div className="packer-visuals"><div className="packer-canvas"><ViewBoundary><Suspense fallback={<p>Loading 3D view…</p>}><Canvas camera={{ position: [400, 330, 420], fov: 45, near: 1, far: 5000 }} onPointerMissed={() => setSelected(null)}><Scene position={position} selected={selected} onSelect={setSelected} /></Canvas></Suspense></ViewBoundary><span className="packer-forward">● Red edge = forward / container back wall</span></div><CrossSection position={position} clearance={clearance} /></div>
    {box && <div className="packer-selection"><strong>{box.box_id} · {box.box_type}</strong><span>{box.deck} {box.position} · Layer {box.layer} / Slot {box.slot} · {box.dims_cm} cm</span><span>{fmt(box.actual_kg)} kg actual · {fmt(box.volume_kg)} kg volume · {fmt(box.chargeable_kg)} kg chargeable{box.leans ? ' · Wall-supported' : ''}{box.upright ? ' · This side up' : ''}</span></div>}
  </section>
}
