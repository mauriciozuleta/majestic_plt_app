import { useState } from 'react'
import { Field } from './components'
import LabelPreview from './LabelPreview'
import { download, request } from './api'

export default function ExportPanel({ plan, setPlan, save, result, deck, position, onError, disabled }) {
  const [scope, setScope] = useState(deck ? 'position' : 'aircraft')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const effectiveScope = deck ? scope : 'aircraft'
  const boxes = (result?.boxes || []).filter(b => (effectiveScope === 'aircraft' || b.deck === deck) && (effectiveScope !== 'position' || b.position === position))
  const run = async file => {
    setBusy(true)
    try {
      const saved = await save()
      await download(saved.id, file, { scope: effectiveScope, ...(deck ? { deck, position } : {}), format: plan.settings.label_format })
    } catch (e) { onError(e.message) } finally { setBusy(false) }
  }
  const showPreview = async () => {
    setBusy(true)
    try { setPreview({ plan, steps: await request('/workorder/preview', plan) }) } catch (e) { onError(e.message) } finally { setBusy(false) }
  }
  return <section className="packer-card"><div className="packer-section-head"><h3>Labels & load work order</h3><label className="packer-field"><span>Export scope</span><select value={effectiveScope} onChange={e => setScope(e.target.value)}><option value="aircraft">Whole aircraft</option>{deck && <><option value="deck">All loaded positions on this deck</option><option value="position">Selected position</option></>}</select></label></div>
    <div className="packer-fields">{[['leader', 'Loader team leader (required for work order)'], ['flight', 'Flight / reference'], ['registration', 'Registration'], ['date', 'Date']].map(([key, label]) => <Field key={key} label={label} type={key === 'date' ? 'date' : 'text'} value={plan.manifest[key]} onChange={v => setPlan(p => ({ ...p, manifest: { ...p.manifest, [key]: v } }))} />)}
      <label className="packer-field"><span>Label format</span><select value={plan.settings.label_format} onChange={e => setPlan(p => ({ ...p, settings: { ...p.settings, label_format: e.target.value } }))}><option value="letter10">Letter · 10 labels</option><option value="a4-8">A4 · 8 labels</option><option value="4x6">4 × 6 thermal</option></select></label>
    </div><label className="packer-field"><span>Load notes</span><textarea rows="2" value={plan.manifest.notes} onChange={e => setPlan(p => ({ ...p, manifest: { ...p.manifest, notes: e.target.value } }))} /></label>
    <div className="packer-actions"><button disabled={busy || disabled} onClick={showPreview}>Preview build instructions</button><button disabled={busy || disabled} onClick={() => run('workorder.pdf')}>Work order PDF</button><button disabled={busy || disabled} onClick={() => run('labels.pdf')}>Labels PDF ({boxes.length})</button><button disabled={busy || disabled} onClick={() => run('boxes.csv')}>Export CSV</button></div>
    <p className="packer-muted">Exports save the current plan. Release separately to publish barcode slot records.</p>
    {!!boxes.length && <LabelPreview boxes={boxes} plan={plan} />}
    {preview?.plan === plan && <div className="packer-preview"><button onClick={() => setPreview(null)}>Close preview</button>{preview.steps.filter(p => (effectiveScope === 'aircraft' || p.deck === deck) && (effectiveScope !== 'position' || p.position === position)).map(p => <article key={`${p.deck}-${p.position}`}><h4>{p.deck} {p.position}</h4><ol>{p.steps.map((step, i) => <li key={i}>{step}</li>)}</ol></article>)}</div>}
  </section>
}
