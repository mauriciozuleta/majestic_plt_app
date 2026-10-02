import { useEffect, useRef, useState } from 'react'

export default function SelectAircraftDialog({ aircraft, onSave, onClose }) {
  const dialogRef = useRef(null)
  const [selected, setSelected] = useState([])
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { dialogRef.current.showModal() }, [])
  const available = aircraft.filter(a => !a.in_fleet)
  const visible = available.filter(a => `${a.manufacturer} ${a.model} ${a.short_name}`.toLowerCase().includes(search.toLowerCase()))
  const toggle = id => setSelected(ids => ids.includes(id) ? ids.filter(i => i !== id) : [...ids, id])
  const save = async e => {
    e.preventDefault()
    if (busy || !selected.length) return
    setBusy(true); setError('')
    try { await onSave(selected); onClose() } catch (err) { setError(err.message); setBusy(false) }
  }
  return <dialog ref={dialogRef} className="fleet-selection-dialog" aria-labelledby="fleet-selection-title" onCancel={e => { e.preventDefault(); if (!busy) onClose() }}>
    <form onSubmit={save}>
      <h3 id="fleet-selection-title">Add existing aircraft</h3><p>Select one or more aircraft to make them available to FRESH24 charter providers.</p>
      <input className="fleet-search" aria-label="Search available aircraft" placeholder="Search manufacturer, model or short name" value={search} onChange={e => setSearch(e.target.value)} disabled={busy} />
      <div className="fleet-selection-list">{visible.map(a => <label key={a.id}><input type="checkbox" checked={selected.includes(a.id)} onChange={() => toggle(a.id)} disabled={busy} /><span><strong>{a.short_name}</strong> · {a.manufacturer} {a.model}</span></label>)}</div>
      {!visible.length && <p>{available.length ? 'No aircraft match your search.' : 'All existing aircraft are already selected. Create additional aircraft in Aircraft Database below.'}</p>}
      {error && <p className="air-logistics__error" role="alert">{error}</p>}
      <div className="air-logistics__actions"><button type="button" className="air-logistics__btn" disabled={busy} onClick={onClose}>Cancel</button><button type="submit" className="air-logistics__btn air-logistics__btn--primary" disabled={busy || !selected.length}>{busy ? 'Adding…' : `Add selected aircraft (${selected.length})`}</button></div>
    </form>
  </dialog>
}
