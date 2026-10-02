import { useState } from 'react'
import { lookupAirportByIata } from '../../../../../services/airports'
import { PROVIDER_TYPES } from './providerTypes'

function CharterProviderModal({ provider, countries, aircraftList, fleetLinked = false, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: provider?.name ?? '',
    country_name: provider?.country_name ?? '',
    main_base_iata: provider?.main_base_iata ?? '',
    aircraft_id: provider?.aircraft_id ?? (fleetLinked && aircraftList.length === 1 ? aircraftList[0].id : ''),
    block_hour_cost: provider?.block_hour_cost ?? '',
    provider_type: provider?.provider_type ?? 'charter',
  })
  // The airport the IATA code resolved to: {name, city, country} or null.
  const [airport, setAirport] = useState(
    provider ? { name: provider.main_base_name, city: provider.main_base_city, country: provider.main_base_country } : null,
  )
  const [airportStatus, setAirportStatus] = useState(provider?.main_base_iata ? 'found' : 'idle')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const selectedAircraft = aircraftList.find(item => item.id === form.aircraft_id)

  const setField = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))

  const handleIataChange = (event) => {
    const code = event.target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3)
    setForm((prev) => ({ ...prev, main_base_iata: code }))
    setAirport(null)
    setAirportStatus('idle')
    if (code.length !== 3) return
    setAirportStatus('loading')
    lookupAirportByIata(code)
      .then((found) => {
        setAirport(found)
        setAirportStatus('found')
        // Pre-select the airport's country when none is chosen yet.
        setForm((prev) => {
          if (prev.country_name || !countries.some((c) => c.name === found.country)) return prev
          return { ...prev, country_name: found.country }
        })
      })
      .catch(() => setAirportStatus('not_found'))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!form.name.trim() || !form.country_name || !form.aircraft_id || (!provider?.source_company_id && form.block_hour_cost === '')) {
      setError('Name, country, aircraft and block hour cost are required.')
      return
    }
    if (airportStatus !== 'found' && (form.main_base_iata || !provider?.source_company_id)) {
      setError('Enter the 3-letter IATA code of a real airport for the main base.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave({
        name: form.name.trim(),
        country_name: form.country_name,
        main_base_iata: form.main_base_iata || null,
        main_base_name: airport?.name ?? null,
        main_base_city: airport?.city ?? null,
        main_base_country: airport?.country ?? null,
        aircraft_id: form.aircraft_id,
        block_hour_cost: form.block_hour_cost === '' ? null : Number(form.block_hour_cost),
        provider_type: form.provider_type,
      })
    } catch (err) {
      setError(err.message || 'Could not save the charter provider.')
      setSaving(false)
    }
  }

  return (
    <div className="revenue-stream-modal__overlay">
      <div className="revenue-stream-modal air-logistics-modal">
        <h3>{provider ? 'Edit Charter Provider' : 'Add Charter Provider'}</h3>
        {fleetLinked && <p className="air-logistics-modal__hint">Choose from all aircraft created in the Aircraft Database. Specifications stay synchronized with Fleet Management.</p>}
        <form className="revenue-stream-modal__form" onSubmit={handleSubmit}>
          <div className="air-logistics-modal__grid">
            <label>
              Name
              <input type="text" value={form.name} onChange={setField('name')} placeholder="e.g. Caribbean Air Cargo" />
            </label>
            <label>
              Country
              <select value={form.country_name} onChange={setField('country_name')}>
                <option value="">Select a country…</option>
                {countries.map((country) => (
                  <option key={country.name} value={country.name}>
                    {country.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Main base (IATA)
              <input type="text" value={form.main_base_iata} onChange={handleIataChange} placeholder="e.g. MIA" />
              <span className="air-logistics-modal__airport">
                {airportStatus === 'loading' && 'Looking up…'}
                {airportStatus === 'not_found' && 'No airport found for this code.'}
                {airportStatus === 'found' && airport && `${airport.name}${airport.city ? `, ${airport.city}` : ''}`}
              </span>
            </label>
            <label>
              {fleetLinked ? 'Aircraft — Aircraft Database' : 'Aircraft'}
              <select value={form.aircraft_id} onChange={setField('aircraft_id')} disabled={aircraftList.length === 0}>
                <option value="">{aircraftList.length ? 'Select an aircraft…' : 'Add an aircraft first'}</option>
                {aircraftList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.short_name} ({item.manufacturer} {item.model})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Block hour cost (USD)
              <input type="number" step="0.01" min="0" value={form.block_hour_cost} onChange={setField('block_hour_cost')} />
            </label>
            <label>
              Type
              <select value={form.provider_type} onChange={setField('provider_type')}>
                {PROVIDER_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {selectedAircraft && fleetLinked && <p className="air-logistics-modal__hint">{selectedAircraft.short_name} · Max payload: {Number(selectedAircraft.max_payload_kg).toLocaleString()} kg · Main / lower deck positions: {selectedAircraft.cargo_positions_main_deck} / {selectedAircraft.cargo_positions_lower_deck} · Fuel burn: {Number(selectedAircraft.fuel_burn_gal_hr).toLocaleString()} gal/h</p>}

          {airport && form.country_name && airport.country && airport.country !== form.country_name && (
            <p className="air-logistics-modal__hint">
              Note: the main base is in {airport.country}, not {form.country_name}.
            </p>
          )}
          {error && <div className="revenue-stream-modal__error">{error}</div>}

          <div className="revenue-stream-modal__actions">
            <button type="button" className="revenue-stream-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="revenue-stream-modal__save" disabled={saving}>
              {saving ? 'Saving…' : provider ? 'Save Changes' : 'Save Provider'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CharterProviderModal
