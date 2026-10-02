import { useState } from 'react'
import { Field } from './components'

function ContourPoints({ contour, onChange }) {
  return <div className="packer-table-wrap"><table><thead><tr><th>Height cm (est.)</th><th>Full width cm (est.)</th><th /></tr></thead><tbody>{contour.points.map((point, i) => <tr key={i}>{point.map((v, j) => <td key={j}><input aria-label={`Point ${i + 1} ${j ? 'width' : 'height'}`} type="number" min="0" step="any" value={v} onChange={e => onChange({ ...contour, points: contour.points.map((p, k) => k === i ? p.map((n, l) => l === j ? Number(e.target.value) : n) : p) })} /></td>)}<td><button onClick={() => onChange({ ...contour, points: contour.points.filter((_, k) => k !== i) })}>Remove point</button></td></tr>)}</tbody></table><button onClick={() => onChange({ ...contour, points: [...contour.points, [(contour.points.at(-1)?.[0] || 0) + 20, contour.points.at(-1)?.[1] || 100]] })}>+ Add point</button></div>
}

export default function AircraftDeckEditor({ deck, onChange }) {
  const [selected, setSelected] = useState(deck.default_contour)
  const [rebuild, setRebuild] = useState({ count: deck.positions.length, prefix: 'P', first: 8.5, spacing: 2.26, max: 2494 })
  const key = deck.contours[selected] ? selected : deck.default_contour
  const contour = deck.contours[key]
  const update = (field, value) => onChange({ ...deck, [field]: value })
  const updateContour = c => update('contours', { ...deck.contours, [key]: c })
  const copy = () => {
    const id = `contour-${Date.now()}`
    update('contours', { ...deck.contours, [id]: { ...structuredClone(contour), name: `${contour.name} copy` } })
    setSelected(id)
  }
  const remove = () => {
    const contours = { ...deck.contours }
    delete contours[key]
    const next = Object.keys(contours)[0]
    onChange({ ...deck, contours, default_contour: deck.default_contour === key ? next : deck.default_contour, positions: deck.positions.map(p => p.contour === key ? { ...p, contour: null } : p) })
    setSelected(next)
  }
  return <><div className="packer-fields">
    <Field label="ULD name" type="text" value={deck.uld} onChange={v => update('uld', v)} /><label className="packer-field"><span>Kind</span><select value={deck.kind} onChange={e => update('kind', e.target.value)}><option value="pallet">Pallet</option><option value="container">Container</option></select></label>
    <Field label="Position length cm (est.)" value={deck.position_length_cm} onChange={v => update('position_length_cm', v)} />
    <Field label="Door width cm (est.)" value={deck.door?.width} nullable onChange={v => update('door', v == null ? null : { width: v, height: deck.door?.height || 100 })} />
    <Field label="Door height cm (est.)" value={deck.door?.height} nullable onChange={v => update('door', v == null ? null : { height: v, width: deck.door?.width || 100 })} />
  </div><h4>Contour library · estimated geometry</h4><div className="packer-actions"><select aria-label="Contour" value={key} onChange={e => setSelected(e.target.value)}>{Object.entries(deck.contours).map(([id, c]) => <option key={id} value={id}>{c.name}{id === deck.default_contour ? ' (default)' : ''}</option>)}</select><button onClick={copy}>Copy contour</button><button disabled={Object.keys(deck.contours).length < 2} onClick={remove}>Remove contour</button><button onClick={() => update('default_contour', key)}>Set default</button></div>
    <Field label="Contour name" type="text" value={contour.name} onChange={v => updateContour({ ...contour, name: v })} /><ContourPoints contour={contour} onChange={updateContour} />
    <h4>Positions · forward to aft · arms are estimates</h4><details><summary>Rebuild position list</summary><div className="packer-fields">{[['count', 'Count (0–60)'], ['prefix', 'ID prefix'], ['first', 'First arm m'], ['spacing', 'Spacing m'], ['max', 'Max kg per position']].map(([k, label]) => <Field key={k} label={label} type={k === 'prefix' ? 'text' : 'number'} value={rebuild[k]} onChange={v => setRebuild(r => ({ ...r, [k]: v }))} />)}<button onClick={() => update('positions', Array.from({ length: Math.max(0, Math.min(60, Math.floor(rebuild.count))) }, (_, i) => ({ id: `${rebuild.prefix}${i + 1}`, arm: Number((rebuild.first + i * rebuild.spacing).toFixed(3)), max_kg: rebuild.max, contour: null })))}>Rebuild list</button></div></details>
    <div className="packer-table-wrap"><table><thead><tr><th>ID</th><th>Arm m (est.)</th><th>Max kg</th><th>Contour override</th><th /></tr></thead><tbody>{deck.positions.map((p, i) => <tr key={i}>
      {['id', 'arm', 'max_kg'].map(k => <td key={k}><input aria-label={`Position ${i + 1} ${k}`} type={k === 'id' ? 'text' : 'number'} value={p[k] ?? ''} step="any" onChange={e => update('positions', deck.positions.map((pos, n) => n === i ? { ...pos, [k]: k === 'id' ? e.target.value : e.target.value === '' ? null : Number(e.target.value) } : pos))} /></td>)}
      <td><select aria-label={`Position ${p.id} contour override`} value={p.contour || ''} onChange={e => update('positions', deck.positions.map((pos, n) => n === i ? { ...pos, contour: e.target.value || null } : pos))}><option value="">Deck default</option>{Object.entries(deck.contours).map(([id, c]) => <option key={id} value={id}>{c.name}</option>)}</select></td><td><button onClick={() => update('positions', deck.positions.filter((_, n) => n !== i))}>Remove</button></td></tr>)}</tbody></table></div>
  </>
}
