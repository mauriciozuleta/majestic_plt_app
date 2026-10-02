import { Field, Toggle } from './components'
import { colors, fmt } from './format'

export default function BoxControls({ plan, setPlan, deck, position, result }) {
  const allocation = plan.alloc[deck]?.[position] || {}
  const updateBox = (index, key, value) => setPlan(p => ({ ...p, box_types: p.box_types.map((b, i) => i === index ? { ...b, [key]: value } : b) }))
  const updateAlloc = (index, key, value) => setPlan(p => ({ ...p, alloc: { ...p.alloc, [deck]: { ...p.alloc[deck], [position]: { ...allocation, [index]: { on: false, qty: null, ...allocation[index], [key]: value } } } } }))
  const removeBox = index => setPlan(p => {
    const alloc = Object.fromEntries(Object.entries(p.alloc).map(([d, positions]) => [d, Object.fromEntries(Object.entries(positions).map(([pos, entries]) => [pos, Object.fromEntries(Object.entries(entries).filter(([i]) => Number(i) !== index).map(([i, v]) => [Number(i) > index ? Number(i) - 1 : i, v]))]))]))
    return { ...p, alloc, box_types: p.box_types.filter((_, i) => i !== index) }
  })
  return <section className="packer-card"><div className="packer-section-head"><div><h3>Box catalogue & allocation</h3><p>Catalogue shared by both decks · Allocation for <strong>{position}</strong></p></div><button onClick={() => setPlan(p => ({ ...p, box_types: [...p.box_types, { name: `Box ${p.box_types.length + 1}`, l: 40, w: 30, h: 20, kg: 5, max_layers: 30, upright: true }] }))}>+ Add box type</button></div>
    <div className="packer-table-wrap"><table className="packer-catalogue"><thead><tr>{['Load', 'Box type', 'L cm', 'W cm', 'H cm', 'Actual kg', 'Max layers', 'Upright', 'Quantity', 'Volume / chargeable kg', ''].map((h, i) => <th key={i}>{h}</th>)}</tr></thead><tbody>
      {plan.box_types.map((b, i) => <tr key={i}><td><input aria-label={`Load ${b.name} at ${position}`} type="checkbox" checked={allocation[i]?.on || false} onChange={e => updateAlloc(i, 'on', e.target.checked)} /></td>
        <td><span style={{ color: colors[i % colors.length] }}>● </span><input aria-label={`Box ${i + 1} name`} value={b.name} onChange={e => updateBox(i, 'name', e.target.value)} /></td>
        {['l', 'w', 'h', 'kg', 'max_layers'].map(key => <td key={key}><input type="number" min={key === 'kg' ? 0 : key === 'max_layers' ? 1 : 5} step="any" aria-label={`${b.name} ${key}`} value={b[key]} onChange={e => updateBox(i, key, Number(e.target.value))} /></td>)}
        <td><input type="checkbox" aria-label={`${b.name} upright only`} checked={b.upright} onChange={e => updateBox(i, 'upright', e.target.checked)} /></td><td><input type="number" min="0" step="1" aria-label={`${b.name} quantity at ${position}`} placeholder="As many as fit" value={allocation[i]?.qty ?? ''} onChange={e => updateAlloc(i, 'qty', e.target.value === '' ? null : Number(e.target.value))} /></td>
        <td className={result?.type_weights[i]?.volume_kg > b.kg ? 'packer-amber' : ''}>{fmt(result?.type_weights[i]?.volume_kg)} / {fmt(result?.type_weights[i]?.chargeable_kg)}{result?.type_weights[i]?.volume_kg > b.kg && <small> Volume exceeds actual</small>}</td><td><button aria-label={`Remove ${b.name}`} onClick={() => removeBox(i)}>×</button></td></tr>)}
    </tbody></table></div><div className="packer-actions"><span className="packer-muted">Blank quantity = as many as fit. Dimensions are in centimetres.</span><button onClick={() => setPlan(p => ({ ...p, alloc: { ...p.alloc, [deck]: Object.fromEntries(p.aircraft.decks[deck].positions.map(pos => [pos.id, structuredClone(allocation)])) } }))}>Copy to all positions on this deck</button><button onClick={() => setPlan(p => ({ ...p, alloc: { ...p.alloc, [deck]: { ...p.alloc[deck], [position]: {} } } }))}>Clear allocation</button></div>
  </section>
}

export function PackingRules({ plan, setPlan, deck }) {
  const settings = plan.settings
  const update = (key, value) => setPlan(p => ({ ...p, settings: { ...p.settings, [key]: value } }))
  const deckUpdate = (key, value) => update(deck, { ...settings[deck], [key]: value })
  return <details className="packer-card"><summary>Packing rules, clearances & box IDs</summary><div className="packer-fields">
    <Field label="Volume divisor (cm³/kg)" value={settings.divisor} onChange={v => update('divisor', v)} min="1" />
    <Field label="Minimum support %" value={settings.min_support} onChange={v => update('min_support', v)} min="1" max="100" />
    <label className="packer-field"><span>Layer priority</span><select value={settings.order} onChange={e => update('order', e.target.value)}><option value="heavy">Heavy / dense first</option><option value="space">Space efficiency</option></select></label>
    <Field label={`${deck} side clearance cm`} value={settings[deck].side_clearance} onChange={v => deckUpdate('side_clearance', v)} min="0" />
    <Field label={`${deck} end clearance cm`} value={settings[deck].end_clearance} onChange={v => deckUpdate('end_clearance', v)} min="0" />
    <Field label="Box ID prefix (unique per released plan)" type="text" value={settings.id_prefix} onChange={v => update('id_prefix', v)} />
    <Field label="ID digits" value={settings.id_digits} onChange={v => update('id_digits', v)} min="1" max="10" />
    <Toggle label="Interlock alternating layers" value={settings.interlock} onChange={v => update('interlock', v)} /><Toggle label="Strict density order" value={settings.strict_density} onChange={v => update('strict_density', v)} />
    {plan.aircraft.decks[deck].kind === 'container' && <><Toggle label="Allow support from sloped walls" value={settings[deck].lean} onChange={v => deckUpdate('lean', v)} /><Field label="Wall-supported minimum support %" value={settings[deck].lean_min_support} onChange={v => deckUpdate('lean_min_support', v)} min="0" max="100" /></>}
  </div></details>
}
