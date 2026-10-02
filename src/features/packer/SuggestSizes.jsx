import { useState } from 'react'
import { request } from './api'
import { Field, Toggle } from './components'
import { fmt } from './format'

export default function SuggestSizes({ plan, deck, position, setPlan, onError }) {
  const [ranges, setRanges] = useState({ l: { minimum: 40, maximum: 80 }, w: { minimum: 30, maximum: 60 }, h: { minimum: 20, maximum: 40 }, step: 10, density: 200, max_kg: 25, upright: true })
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const search = async () => {
    setBusy(true)
    setResults([])
    try { setResults(await request('/suggest', { plan, deck, position, ...ranges })) } catch (e) { onError(e.message) } finally { setBusy(false) }
  }
  const addSize = size => setPlan(p => ({ ...p, box_types: [...p.box_types, { name: `${size.l} × ${size.w} × ${size.h} carton`, l: size.l, w: size.w, h: size.h, kg: size.kg, upright: ranges.upright, max_layers: 30 }], alloc: { ...p.alloc, [deck]: { ...p.alloc[deck], [position]: { ...p.alloc[deck]?.[position], [p.box_types.length]: { on: true, qty: null } } } } }))
  return <details className="packer-card"><summary>Suggest box sizes</summary><p className="packer-muted">Rank sizes by loaded volume at {position}. Search is capped at 20,000 combinations.</p><div className="packer-fields">
    {['l', 'w', 'h'].flatMap(dim => ['minimum', 'maximum'].map(bound => <Field key={`${dim}-${bound}`} label={`${dim.toUpperCase()} ${bound} cm`} value={ranges[dim][bound]} onChange={v => setRanges(r => ({ ...r, [dim]: { ...r[dim], [bound]: v } }))} min="5" />))}
    {[['step', 'Step cm'], ['density', 'Packed density kg/m³'], ['max_kg', 'Maximum kg per box']].map(([key, label]) => <Field key={key} label={label} value={ranges[key]} onChange={v => setRanges(r => ({ ...r, [key]: v }))} min="0.1" />)}
    <Toggle label="Upright only" value={ranges.upright} onChange={v => setRanges(r => ({ ...r, upright: v }))} /><button disabled={busy} onClick={search}>{busy ? 'Searching…' : 'Find best sizes'}</button></div>
    {!!results.length && <div className="packer-table-wrap"><table><thead><tr><th>Size cm</th><th>Boxes</th><th>Fill</th><th>Loaded kg</th><th>Limit</th><th /></tr></thead><tbody>{results.map((r, i) => <tr key={i}><td>{r.l} × {r.w} × {r.h}</td><td>{r.count}</td><td>{fmt(r.fill_pct)}%</td><td>{fmt(r.loaded_kg)}</td><td>{r.weight_limited ? 'Weight-limited' : 'Geometry'}</td><td><button onClick={() => addSize(r)}>Use</button></td></tr>)}</tbody></table></div>}
  </details>
}
