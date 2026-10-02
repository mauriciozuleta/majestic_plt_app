import { useEffect, useState } from 'react'
import { deleteAircraft, fetchAircraft, saveAircraft } from '../../../../../services/airLogistics'
import AircraftModal from './AircraftModal'
import './AirLogistics.css'

const formatNumber = (value, digits = 0) =>
  value == null ? '—' : Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })

export default function AircraftCatalogue({ companyId, onChanged }) {
  const [aircraftList, setAircraftList] = useState([])
  const [selectedAircraftId, setSelectedAircraftId] = useState(null)
  const [aircraftModal, setAircraftModal] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    fetchAircraft(companyId).then(items => { if (!cancelled) setAircraftList(items) })
      .catch(err => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [companyId])
  const reload = async () => {
    setAircraftList(await fetchAircraft(companyId))
    await onChanged?.()
  }
  const handleSaveAircraft = async payload => {
    const saved = await saveAircraft(companyId, aircraftModal === 'add' ? null : aircraftModal.id, payload)
    setAircraftModal(null)
    setSelectedAircraftId(saved.id)
    await reload()
  }
  const selectedAircraft = aircraftList.find(item => item.id === selectedAircraftId)
  const handleDeleteAircraft = async () => {
    if (!selectedAircraft || !window.confirm(`Delete aircraft "${selectedAircraft.short_name}"?`)) return
    setError('')
    try {
      await deleteAircraft(companyId, selectedAircraft.id)
      setSelectedAircraftId(null)
      await reload()
    } catch (err) { setError(err.message) }
  }
  if (loading) return <p className="air-logistics__empty">Loading aircraft…</p>
  return <div>
    {error && <div className="air-logistics__error" role="alert">{error}</div>}
      <section className="air-logistics__section">
        <h4>Aircraft</h4>
        <p>Aircraft types the charter providers fly — weights in kg, fuel in US gallons.</p>
        <div className="air-logistics__table-wrap">
          <table className="air-logistics__table">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Manufacturer</th>
                <th className="num">MTOW (kg)</th>
                <th className="num">Max Payload (kg)</th>
                <th className="num">Fuel Burn (gal/h)</th>
                <th className="num">Positions (Main / Lower)</th>
                <th className="num">Cruise (kt)</th>
                <th className="num">Range @ Max Payload (nm)</th>
              </tr>
            </thead>
            <tbody>
              {aircraftList.map((item) => (
                <tr
                  key={item.id}
                  className={item.id === selectedAircraftId ? 'is-selected' : ''}
                  onClick={() => setSelectedAircraftId(item.id === selectedAircraftId ? null : item.id)}
                >
                  <td>
                    {item.short_name} ({item.model})
                  </td>
                  <td>{item.manufacturer}</td>
                  <td className="num">{formatNumber(item.mtow_kg)}</td>
                  <td className="num">{formatNumber(item.max_payload_kg)}</td>
                  <td className="num">{formatNumber(item.fuel_burn_gal_hr)}</td>
                  <td className="num">
                    {item.cargo_positions_main_deck} / {item.cargo_positions_lower_deck}
                  </td>
                  <td className="num">{formatNumber(item.cruise_speed_kt)}</td>
                  <td className="num">{formatNumber(item.max_range_at_max_payload_nm)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {aircraftList.length === 0 && <div className="air-logistics__empty">No aircraft yet — add one before creating a charter provider.</div>}
        </div>
        <div className="air-logistics__actions">
          <button type="button" className="air-logistics__btn air-logistics__btn--primary" onClick={() => setAircraftModal('add')}>
            Add Aircraft
          </button>
          <button type="button" className="air-logistics__btn" onClick={() => setAircraftModal(selectedAircraft)} disabled={!selectedAircraft}>
            Edit Selected
          </button>
          <button type="button" className="air-logistics__btn air-logistics__btn--danger" onClick={handleDeleteAircraft} disabled={!selectedAircraft}>
            Delete Selected
          </button>
        </div>
      </section>

    {aircraftModal && <AircraftModal aircraft={aircraftModal === 'add' ? null : aircraftModal} onSave={handleSaveAircraft} onCancel={() => setAircraftModal(null)} />}
  </div>
}
