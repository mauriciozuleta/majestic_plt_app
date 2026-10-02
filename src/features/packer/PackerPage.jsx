import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { request, newPlan } from './api'
import { Tabs, Stats, PositionStrip, PositionTable } from './components'
import BoxControls, { PackingRules } from './BoxControls'
import SuggestSizes from './SuggestSizes'
import ExportPanel from './ExportPanel'
import AircraftEditor from './AircraftEditor'
import SaveConfigurationDialog from './SaveConfigurationDialog'
import './packer.css'

const PositionView = lazy(() => import('./PositionView'))

export default function PackerPage({ companyId }) {
  const [aircraft, setAircraft] = useState([])
  const [plans, setPlans] = useState([])
  const [plan, setPlan] = useState(null)
  const [result, setResult] = useState(null)
  const [tab, setTab] = useState('overview')
  const [positions, setPositions] = useState({ main: 'P1', lower: 'F1' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [packing, setPacking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [editor, setEditor] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saveDialog, setSaveDialog] = useState(null)
  const planRef = useRef(plan)
  const generation = useRef(0)
  useEffect(() => { planRef.current = plan }, [plan])

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([request('/aircraft', undefined, { signal: controller.signal }), request(`/plans?company_id=${encodeURIComponent(companyId)}`, undefined, { signal: controller.signal })])
      .then(([a, p]) => { setAircraft(a); setPlans(p); setPlan(newPlan(companyId, a[0])) })
      .catch(e => { if (e.name !== 'AbortError') setError(e.message) })
    return () => controller.abort()
  }, [companyId])

  const editPlan = useCallback(update => {
    setPlan(p => typeof update === 'function' ? update(p) : update)
    setDirty(true); setNotice(''); setResult(null)
  }, [])

  useEffect(() => {
    if (!plan) return
    const controller = new AbortController()
    const version = ++generation.current
    const timer = setTimeout(() => {
      setPacking(true)
      request('/pack', plan, { signal: controller.signal })
      .then(value => { if (generation.current === version) { setResult(value); setError('') } })
      .catch(e => { if (e.name !== 'AbortError' && generation.current === version) { setError(e.message); setResult(null) } })
      .finally(() => { if (generation.current === version) setPacking(false) })
    }, 80)
    return () => { clearTimeout(timer); controller.abort() }
  }, [plan])

  useEffect(() => {
    const handler = e => { if (dirty) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const save = async (asNew = false, name) => {
    const current = planRef.current
    const configuration = { ...current, name: name ?? current.name }
    const saved = await request('/plans', asNew ? { ...configuration, id: null, version: 0 } : configuration)
    if (planRef.current === current) { setPlan(saved); setDirty(false) }
    else setPlan(p => ({ ...p, id: saved.id, version: saved.version }))
    setPlans(p => [{ id: saved.id, name: saved.name, version: saved.version }, ...p.filter(v => v.id !== saved.id)])
    setNotice(`Configuration “${saved.name}” saved to the database.`)
    return saved
  }
  const action = async fn => {
    setBusy(true); setError('')
    try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const release = async () => {
    const saved = await save()
    try { await request(`/plans/${saved.id}/release`, { confirm_reassign: false }) }
    catch (e) {
      if (e.message.startsWith('Box IDs will be reassigned') && window.confirm(e.message)) await request(`/plans/${saved.id}/release`, { confirm_reassign: true })
      else throw e
    }
    setNotice('Plan released. Barcode slot records are available to the box-detail app.')
  }
  const switchPlan = async id => {
    if (dirty && !window.confirm('Discard unsaved changes and switch plans?')) return
    const next = id ? await request(`/plans/${id}`) : newPlan(companyId, aircraft[0])
    setPlan(next); setDirty(false); setResult(null); setNotice('')
  }
  const selectAircraft = a => editPlan(p => ({ ...p, aircraft_id: a.id, aircraft: a, alloc: { main: {}, lower: {} } }))
  const useAircraft = async (a, persisted) => {
    if (persisted) setAircraft(await request('/aircraft'))
    editPlan(p => ({ ...p, aircraft_id: a.id, aircraft: a, alloc: Object.fromEntries(['main', 'lower'].map(d => [d, Object.fromEntries(Object.entries(p.alloc[d] || {}).filter(([id]) => a.decks[d].positions.some(pos => pos.id === id)))])) }))
    setEditor(null)
  }
  const openPosition = (deck, pos) => { setTab(deck); setPositions(p => ({ ...p, [deck]: pos })) }
  if (!plan) return <div className="packer"><p role={error ? 'alert' : 'status'}>{error || 'Loading Cargo Load Operations…'}</p></div>
  const deck = tab === 'lower' ? 'lower' : 'main'
  const deckPositions = result?.positions.filter(p => p.deck === deck) || []
  const selectedId = plan.aircraft.decks[deck].positions.some(p => p.id === positions[deck]) ? positions[deck] : plan.aircraft.decks[deck].positions[0]?.id
  const selected = deckPositions.find(p => p.position === selectedId)
  const selectOptions = aircraft.some(a => a.id === plan.aircraft_id) ? aircraft : [...aircraft, plan.aircraft]
  return <div className="packer" aria-busy={packing || busy}>
    <div className="packer-heading"><div><span className="packer-eyebrow">CARGO / LOAD PLANNING</span><h2>Cargo Load Operations</h2><p>Build each position. Label every box. Prepare the loading team.</p></div><span className="packer-status" role="status">{packing ? 'Calculating…' : dirty ? 'Unsaved changes' : 'Plan ready'}</span></div>
    {error && <div className="packer-error" role="alert">{error}</div>}{notice && <div className="packer-success" role="status">{notice}</div>}
    <fieldset disabled={busy} className="packer-workspace"><section className="packer-card packer-toolbar"><label className="packer-field"><span>Aircraft · planning estimates</span><select value={plan.aircraft_id} onChange={e => { if (e.target.value === 'new') setEditor({ ...structuredClone(plan.aircraft), id: crypto.randomUUID(), name: 'New aircraft', builtin: false }); else selectAircraft(aircraft.find(a => a.id === e.target.value)) }}>{selectOptions.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}<option value="new">Add new aircraft…</option></select></label><button onClick={() => setEditor(plan.aircraft)}>Edit aircraft</button>
      <label className="packer-field"><span>Saved configuration</span><select value={plan.id || ''} onChange={e => action(() => switchPlan(e.target.value))}><option value="">New configuration</option>{plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="packer-field"><span>Configuration name</span><input value={plan.name} onChange={e => editPlan(p => ({ ...p, name: e.target.value }))} /></label><button className="packer-primary" onClick={() => setSaveDialog({ asNew: false })}>Save changes</button><button onClick={() => setSaveDialog({ asNew: true })}>Save as new</button><button className="packer-primary" disabled={!result || packing} onClick={() => action(release)}>Release plan</button>
    </section>
    <details className="packer-aircraft-notes"><summary>Aircraft geometry & balance arms are estimates · aircraft notes</summary><p>{plan.aircraft.notes}</p></details>
    <div className="packer-notice">{result?.wb.note || 'Planning estimate only: fuel, crew and bulk hold cargo are not included. The approved load sheet from load control decides.'}{result?.wb.warnings.map(w => <strong key={w}>{w}</strong>)}</div>
    <Tabs label="Load planning deck" panelId="packer-deck-panel" value={tab} onChange={setTab} items={[{ id: 'overview', label: 'Overview' }, { id: 'main', label: 'Main deck', count: result?.decks.main.boxes }, { id: 'lower', label: 'Lower deck', count: result?.decks.lower.boxes }]} />
    <div id="packer-deck-panel" role="tabpanel" aria-label={tab === 'overview' ? 'Overview' : `${deck} deck`} className="packer-content">
      {tab === 'overview' ? <>
        <Stats totals={result?.totals} maximum={plan.aircraft.wb.max_payload_kg} wb={result?.wb} />
        {result && <p className="packer-muted">Weight & balance status: {result.wb.status}</p>}
        {result && <>{['main', 'lower'].map(d => <PositionStrip key={d} deck={d} positions={result.positions.filter(p => p.deck === d)} centroid={result.wb.centroid_m} onSelect={pos => openPosition(d, pos)} />)}<section className="packer-card"><h3>All positions</h3><PositionTable positions={result.positions} onSelect={openPosition} /></section></>}
      </> : <>
        <Stats totals={result?.decks[deck]} />
        <PositionStrip deck={deck} positions={deckPositions} selected={selectedId} onSelect={pos => setPositions(p => ({ ...p, [deck]: pos }))} />
        {selectedId ? <><BoxControls plan={plan} setPlan={editPlan} deck={deck} position={selectedId} result={result} /><PackingRules plan={plan} setPlan={editPlan} deck={deck} /><SuggestSizes key={`${deck}-${selectedId}`} plan={plan} setPlan={editPlan} deck={deck} position={selectedId} onError={setError} />
          {selected && <>{selected.messages.map(m => <div key={m} className="packer-notice">{m}</div>)}<Suspense fallback={<p>Loading position preview…</p>}><PositionView key={`${deck}-${selectedId}`} position={selected} clearance={plan.settings[deck].side_clearance} /></Suspense><section className="packer-card"><h3>Selected position result</h3><PositionTable positions={[selected]} onSelect={openPosition} /></section></>}
        </> : <p>No positions on this deck. Add them in Edit aircraft.</p>}
      </>}
      <ExportPanel key={tab} plan={plan} setPlan={editPlan} save={save} result={result} deck={tab === 'overview' ? null : deck} position={selectedId} onError={setError} disabled={!result || packing} />
    </div></fieldset>
    {saveDialog && <SaveConfigurationDialog initialName={saveDialog.asNew ? `${plan.name} copy` : plan.name} asNew={saveDialog.asNew} onSave={name => save(saveDialog.asNew, name)} onClose={() => setSaveDialog(null)} />}
    {editor && <AircraftEditor aircraft={editor} isSaved={aircraft.some(a => a.id === editor.id)} onClose={() => setEditor(null)} onUse={useAircraft} onDeleted={id => { setAircraft(a => a.filter(item => item.id !== id)); if (plan.aircraft_id === id) selectAircraft(aircraft.find(a => a.id !== id)); setEditor(null) }} />}
  </div>
}
