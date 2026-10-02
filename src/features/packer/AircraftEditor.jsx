import { useEffect, useRef, useState } from 'react'
import { request } from './api'
import { Field, Tabs } from './components'
import AircraftDeckEditor from './AircraftDeckEditor'

export default function AircraftEditor({ aircraft, isSaved, onUse, onClose, onDeleted }) {
  const [draft, setDraft] = useState(() => structuredClone(aircraft))
  const [deck, setDeck] = useState('main')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [aiDraft, setAiDraft] = useState(false)
  const dialogRef = useRef(null)
  useEffect(() => { dialogRef.current.showModal() }, [])
  const use = async persist => {
    setBusy(true); setError('')
    try {
      let value = draft
      if (persist) value = await request(`/aircraft/${draft.id}`, draft, { method: 'PUT' })
      else await request('/pack', { company_id: 'validation', aircraft_id: draft.id, aircraft: draft })
      await onUse(value, persist)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const ai = async () => {
    setBusy(true); setError('')
    try { setDraft(await request('/aircraft/draft', { query })); setAiDraft(true) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm(`Delete saved aircraft “${draft.name}”?`)) return
    setBusy(true)
    try { await request(`/aircraft/${draft.id}`, undefined, { method: 'DELETE' }); onDeleted(draft.id) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <dialog className="packer-modal packer" ref={dialogRef} onCancel={e => { e.preventDefault(); if (!busy) onClose() }} aria-labelledby="aircraft-editor-title"><div className="packer-section-head"><h2 id="aircraft-editor-title">Aircraft configuration</h2><button disabled={busy} onClick={onClose}>Close</button></div>
    <p className="packer-notice">Geometry and balance arms are planning estimates. Replace them with the aircraft’s Weight & Balance Manual.</p>
    {error && <div role="alert" className="packer-error">{error}</div>}
    <div className="packer-fields"><Field label="Aircraft name" type="text" value={draft.name} onChange={v => setDraft(d => ({ ...d, name: v }))} /><Field label="Maximum payload kg" value={draft.wb.max_payload_kg} onChange={v => setDraft(d => ({ ...d, wb: { ...d.wb, max_payload_kg: v } }))} /></div>
    <label className="packer-field"><span>Aircraft notes</span><textarea rows="4" value={draft.notes} onChange={e => setDraft(d => ({ ...d, notes: e.target.value }))} /></label>
    <Tabs label="Aircraft deck editor" items={[{ id: 'main', label: 'Main deck' }, { id: 'lower', label: 'Lower deck' }]} value={deck} onChange={setDeck} />
    <AircraftDeckEditor key={`${draft.id}-${deck}`} deck={draft.decks[deck]} onChange={value => setDraft(d => ({ ...d, decks: { ...d.decks, [deck]: value } }))} />
    <h4>Weight & balance reference data</h4><p className="packer-muted">Leave unknown references blank. CG is unavailable until all required references are supplied.</p><div className="packer-fields">{[['dow_kg', 'Dry operating weight kg'], ['dow_arm_m', 'DOW arm m'], ['lemac_m', 'LEMAC m'], ['mac_m', 'MAC m'], ['fwd_limit_pct_mac', 'Forward limit % MAC'], ['aft_limit_pct_mac', 'Aft limit % MAC']].map(([k, label]) => <Field key={k} label={label} nullable value={draft.wb[k]} onChange={v => setDraft(d => ({ ...d, wb: { ...d.wb, [k]: v } }))} />)}</div>
    <details><summary>Draft specs with AI</summary><p className="packer-muted">Requires backend AI configuration. Review every estimate before saving.</p><div className="packer-actions"><input aria-label="Aircraft to draft" placeholder="Aircraft type and conversion" value={query} onChange={e => setQuery(e.target.value)} /><button disabled={busy || query.length < 3} onClick={ai}>{busy ? 'Working…' : 'Draft specs with AI'}</button></div>{aiDraft && <p className="packer-amber">AI draft loaded for review. It has not been saved.</p>}</details>
    <div className="packer-modal-footer"><button disabled={busy} onClick={onClose}>Cancel</button>{isSaved && !draft.builtin && !aiDraft && <button disabled={busy} onClick={remove}>Delete saved aircraft</button>}<button disabled={busy} onClick={() => use(false)}>Use without saving</button><button className="packer-primary" disabled={busy} onClick={() => use(true)}>Save to database</button></div>
  </dialog>
}
