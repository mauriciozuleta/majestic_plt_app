import { useCallback, useEffect, useState } from 'react'
import { addAircraftToFleet, deleteAircraft, fetchAircraftCatalogue, removeAircraftFromFleet, saveAircraft } from '../../../../../services/airLogistics'
import AircraftModal from '../../FinancialTab/AirLogistics/AircraftModal'
import AircraftTable from './AircraftTable'
import SelectAircraftDialog from './SelectAircraftDialog'
import '../../FinancialTab/AirLogistics/AirLogistics.css'
import './FleetManagement.css'

export default function FleetManagement({ companyId }) {
  const [aircraft, setAircraft] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selectedFleet, setSelectedFleet] = useState(null)
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [selecting, setSelecting] = useState(false)
  const [editing, setEditing] = useState(null)
  const [search, setSearch] = useState('')
  const [databaseExpanded, setDatabaseExpanded] = useState(true)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const reload = useCallback(async () => {
    setAircraft(await fetchAircraftCatalogue(companyId))
  }, [companyId])
  useEffect(() => {
    let cancelled = false
    const refresh = () => fetchAircraftCatalogue(companyId).then(items => { if (!cancelled) { setAircraft(items); setError('') } })
      .catch(err => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    refresh()
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [companyId])
  const refreshDatabase = async () => {
    setRefreshing(true)
    try { await reload(); setError('') } catch (err) { setError(err.message) } finally { setRefreshing(false) }
  }
  const add = async ids => {
    await addAircraftToFleet(companyId, ids)
    await reload()
    setError(''); setNotice(`${ids.length} aircraft added to the fleet and made available to FRESH24 providers.`)
  }
  const save = async payload => {
    const saved = await saveAircraft(companyId, editing === 'add' ? null : editing.id, payload)
    await reload()
    setSelectedRecord(saved.id); setEditing(null); setError('')
    setNotice(editing === 'add' ? 'Aircraft created in the database. Use Add Aircraft in the upper card to select it for the fleet.' : 'Aircraft specifications saved.')
  }
  const remove = async (id, fromDatabase) => {
    if (fromDatabase && !window.confirm('Delete this aircraft from the database?')) return
    setBusy(true); setError(''); setNotice('')
    try {
      if (fromDatabase) { await deleteAircraft(companyId, id); setSelectedRecord(null) }
      else await removeAircraftFromFleet(companyId, id)
      setSelectedFleet(null)
      await reload()
      setNotice(fromDatabase ? 'Aircraft deleted from the database.' : 'Aircraft removed from the fleet. Its database record is retained.')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  if (loading) return <p className="air-logistics__empty">Loading fleet and aircraft database…</p>
  const current = aircraft.find(a => a.id === selectedRecord)
  const visible = aircraft.filter(a => `${a.manufacturer} ${a.model} ${a.short_name} ${a.source_aircraft_id || ''}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="fleet-management">
    {error && <div className="air-logistics__error" role="alert">{error}</div>}{notice && <p className="fleet-notice" role="status">{notice}</p>}
    <section className="air-logistics__section" aria-labelledby="selected-aircraft-title">
      <h4 id="selected-aircraft-title">Aircraft</h4><p>{aircraft.filter(a => a.in_fleet).length} selected fleet aircraft · {aircraft.length} records in the Aircraft Database below. Provider forms can select any aircraft from the database.</p>
      <AircraftTable aircraft={aircraft.filter(a => a.in_fleet)} selectedId={selectedFleet} onSelect={setSelectedFleet} />
      <div className="air-logistics__actions"><button className="air-logistics__btn air-logistics__btn--primary" disabled={busy} onClick={() => setSelecting(true)}>Add Aircraft</button><button className="air-logistics__btn" disabled={busy || !selectedFleet} onClick={() => remove(selectedFleet, false)}>Remove from fleet</button></div>
    </section>
    <section className="air-logistics__section" aria-labelledby="aircraft-database-title">
      <div className="fleet-database-heading"><h4 id="aircraft-database-title"><button type="button" className="fleet-database-toggle" aria-expanded={databaseExpanded} aria-controls="aircraft-database-content" onClick={() => setDatabaseExpanded(expanded => !expanded)}><span className="fleet-database-triangle" aria-hidden="true">{databaseExpanded ? '▾' : '▸'}</span>Aircraft Database</button></h4><span>{aircraft.length} aircraft</span><button className="air-logistics__btn fleet-database-refresh" disabled={refreshing || busy} onClick={refreshDatabase}>{refreshing ? 'Refreshing…' : 'Refresh database'}</button></div>
      <div id="aircraft-database-content" hidden={!databaseExpanded}><p className="fleet-database-description">Aircraft specifications imported from AI_FRESH24 · Administrator Options / Logistics / Air / Aircraft. Create and edit records here, then select them for the fleet above.</p>
      <input className="fleet-search" aria-label="Search aircraft database" placeholder="Search aircraft database" value={search} onChange={e => setSearch(e.target.value)} />
      <AircraftTable aircraft={visible} selectedId={selectedRecord} onSelect={setSelectedRecord} database />
      <div className="air-logistics__actions"><button className="air-logistics__btn air-logistics__btn--primary" disabled={busy} onClick={() => setEditing('add')}>Add Aircraft</button><button className="air-logistics__btn" disabled={busy || !current} onClick={() => setEditing(current)}>Edit Selected</button><button className="air-logistics__btn air-logistics__btn--danger" disabled={busy || !current} onClick={() => remove(current.id, true)}>Delete Selected</button></div>
      </div>
    </section>
    {selecting && <SelectAircraftDialog aircraft={aircraft} onSave={add} onClose={() => setSelecting(false)} />}
    {editing && <AircraftModal aircraft={editing === 'add' ? null : editing} onSave={save} onCancel={() => setEditing(null)} />}
  </div>
}
