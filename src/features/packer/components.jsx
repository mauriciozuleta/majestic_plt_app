import { useId } from 'react'

import { fmt } from './format'

export function Field({ label, value, onChange, type = 'number', nullable = false, ...props }) {
  return <label className="packer-field"><span>{label}</span><input type={type} value={value ?? ''} onChange={e => onChange(type === 'number' ? (e.target.value === '' && nullable ? null : Number(e.target.value)) : e.target.value)} {...props} /></label>
}

export function Toggle({ label, value, onChange }) {
  return <label className="packer-toggle"><input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} />{label}</label>
}

export function Tabs({ items, value, onChange, label, panelId }) {
  const id = useId()
  return <div className="packer-tabs" role="tablist" aria-label={label}>
    {items.map((item, index) => <button key={item.id} id={`${id}-${item.id}`} type="button" role="tab" aria-controls={panelId} aria-selected={item.id === value} tabIndex={item.id === value ? 0 : -1}
      onClick={() => onChange(item.id)} onKeyDown={e => {
        let next
        if (e.key === 'ArrowRight') next = (index + 1) % items.length
        if (e.key === 'ArrowLeft') next = (index + items.length - 1) % items.length
        if (e.key === 'Home') next = 0
        if (e.key === 'End') next = items.length - 1
        if (next !== undefined) { e.preventDefault(); onChange(items[next].id); e.currentTarget.parentElement.children[next].focus() }
      }}>{item.label}{item.count != null && <span className="packer-badge">{fmt(item.count, 0)}</span>}</button>)}
  </div>
}

export function Stats({ totals, height, maximum, wb }) {
  const items = [['Actual payload', `${fmt(totals?.actual_kg)} kg`], ['Volume weight', `${fmt(totals?.volume_kg)} kg`], ['Chargeable', `${fmt(totals?.chargeable_kg)} kg`], ['Boxes', fmt(totals?.boxes, 0)], ['Packed volume', `${fmt(totals?.volume_m3, 2)} m³`]]
  if (maximum != null) items[0][1] += ` / ${fmt(maximum)} kg`
  if (height != null) items.push(['Stack height', `${fmt(height)} cm`])
  if (wb) items.push(['Payload centroid (est.)', `${fmt(wb.centroid_m, 2)} m`], ['Zero-fuel CG (est.)', `${fmt(wb.cg_pct_mac, 2)}% MAC`])
  return <div className="packer-stats">{items.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
}

export function PositionStrip({ deck, positions, selected, onSelect, centroid }) {
  const arms = positions.map(p => p.arm).filter(a => a != null)
  const min = Math.min(...arms), max = Math.max(...arms)
  return <section className="packer-card"><div className="packer-section-head"><h3>{deck === 'main' ? 'Main deck' : 'Lower deck'}</h3><span>Forward → Aft · Arms & geometry are estimates</span></div>
    <div className="packer-position-strip">{positions.map(p => <button key={p.position} className={`${selected === p.position ? 'is-active' : ''} ${p.kg > p.max_kg ? 'is-over' : ''}`}
      style={{ '--load': `${Math.min(100, p.max_kg ? p.kg / p.max_kg * 100 : 0)}%` }} onClick={() => onSelect(p.position)} title={`${p.position}: ${fmt(p.kg)} / ${fmt(p.max_kg)} kg · arm ${fmt(p.arm)} m (est.)`}>
      <strong>{p.position}</strong><small>{fmt(p.kg, 0)} kg</small><small>{p.boxes.length} boxes</small></button>)}</div>
    {centroid != null && max > min && <div className="packer-centroid"><span style={{ left: `${Math.max(0, Math.min(100, (centroid - min) / (max - min) * 100))}%` }}>▲ Payload centroid {fmt(centroid, 2)} m (est.)</span></div>}
    {!positions.length && <p className="packer-muted">No positions configured on this deck.</p>}
  </section>
}

export function PositionTable({ positions, onSelect }) {
  return <div className="packer-table-wrap"><table><thead><tr>{['Deck / position', 'Boxes', 'Actual kg', 'Volume kg', 'Chargeable kg', 'Height cm', 'Fill', 'Arm m (est.)'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>
    {positions.map(p => <tr key={`${p.deck}-${p.position}`}><td><button className="packer-link" onClick={() => onSelect?.(p.deck, p.position)}>{p.deck === 'main' ? 'MD' : 'LWR'} {p.position}</button></td><td>{p.boxes.length}</td><td>{fmt(p.kg)}</td><td>{fmt(p.totals.volume_kg)}</td><td>{fmt(p.totals.chargeable_kg)}</td><td>{fmt(p.height)}</td><td>{fmt(p.contour_m3 ? p.totals.volume_m3 / p.contour_m3 * 100 : 0)}%</td><td>{fmt(p.arm, 2)}</td></tr>)}
  </tbody></table></div>
}
