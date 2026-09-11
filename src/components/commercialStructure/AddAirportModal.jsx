import { useState } from 'react'
import { lookupAirportByIata } from '../../services/airports'
import './AddAirportModal.css'

const emptyFields = {
  iataCode: '',
  name: '',
  city: '',
  country: '',
  latitude: '',
  longitude: '',
  altitudeFt: '',
  fuelCostGl: '',
  cargoHandlingCostKg: '',
  airportFee: '',
  turnaroundCost: '',
  otherDesc: '',
  otherCost: '',
  branchManager: '',
  branchUser: '',
}

function toFieldsFromBranch(branch, countryName) {
  if (!branch) return { ...emptyFields, country: countryName ?? '' }
  return {
    iataCode: branch.airport ?? '',
    name: branch.name ?? '',
    city: branch.city ?? '',
    country: countryName ?? '',
    latitude: branch.latitude ?? '',
    longitude: branch.longitude ?? '',
    altitudeFt: branch.altitude_ft ?? '',
    fuelCostGl: branch.fuel_cost_gl ?? '',
    cargoHandlingCostKg: branch.cargo_handling_cost_kg ?? '',
    airportFee: branch.airport_fee ?? '',
    turnaroundCost: branch.turnaround_cost ?? '',
    otherDesc: branch.other_desc ?? '',
    otherCost: branch.other_cost ?? '',
    branchManager: branch.manager_name ?? '',
    branchUser: branch.user_name ?? '',
  }
}

function AddAirportModal({ mode = 'create', initialBranch = null, countryName = '', onSave, onCancel }) {
  const [fields, setFields] = useState(() => toFieldsFromBranch(initialBranch, countryName))
  const [lookupState, setLookupState] = useState('idle')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const setField = (key, value) => setFields((previous) => ({ ...previous, [key]: value }))

  const handleIataChange = (event) => {
    const value = event.target.value.toUpperCase().slice(0, 3)
    setField('iataCode', value)

    if (value.length !== 3) {
      setLookupState('idle')
      return
    }

    setLookupState('loading')
    // Country is not part of this lookup — it's fixed to the commercial
    // country branch this airport belongs to (see the `country` prop),
    // not whatever the airport database reports, so it's left untouched.
    setFields((previous) => ({ ...previous, name: 'Searching...', city: 'Searching...' }))

    lookupAirportByIata(value)
      .then((data) => {
        setFields((previous) => ({
          ...previous,
          name: data.name || '',
          city: data.city || '',
          latitude: data.latitude ?? '',
          longitude: data.longitude ?? '',
          altitudeFt: data.altitude_ft ?? '',
        }))
        setLookupState('found')
      })
      .catch(() => {
        setFields((previous) => ({
          ...previous,
          name: 'Not Found',
          city: 'Not Found',
          latitude: '',
          longitude: '',
          altitudeFt: '',
        }))
        setLookupState('not-found')
      })
  }

  const numOrNull = (value) => (value === '' || value === null || value === undefined ? null : Number(value))

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (fields.iataCode.length !== 3 || !fields.name.trim() || fields.name === 'Searching...') {
      setError('Enter a valid 3-letter IATA code and airport name.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await onSave({
        name: fields.name === 'Not Found' ? fields.iataCode : fields.name,
        manager_name: fields.branchManager || null,
        user_name: fields.branchUser || null,
        airport: fields.iataCode,
        city: fields.city === 'Not Found' ? null : fields.city || null,
        latitude: numOrNull(fields.latitude),
        longitude: numOrNull(fields.longitude),
        altitude_ft: numOrNull(fields.altitudeFt),
        fuel_cost_gl: numOrNull(fields.fuelCostGl),
        cargo_handling_cost_kg: numOrNull(fields.cargoHandlingCostKg),
        airport_fee: numOrNull(fields.airportFee),
        turnaround_cost: numOrNull(fields.turnaroundCost),
        other_desc: fields.otherDesc || null,
        other_cost: numOrNull(fields.otherCost),
      })
    } catch (err) {
      setError(err.message || 'Could not save the airport')
    } finally {
      setSaving(false)
    }
  }

  const lookingUp = lookupState === 'loading'
  const notFound = lookupState === 'not-found'

  return (
    <div className="add-airport-modal__overlay">
      <div className="add-airport-modal">
        <h3>{mode === 'edit' ? 'Edit Airport' : 'Add Airport'}</h3>
        <form className="add-airport-modal__form" onSubmit={handleSubmit}>
          <section className="add-airport-modal__section">
            <h4>Basic Information</h4>
            <div className="add-airport-modal__grid">
              <label>
                IATA Code
                <input
                  type="text"
                  value={fields.iataCode}
                  onChange={handleIataChange}
                  maxLength={3}
                  placeholder="JFK"
                  required
                />
              </label>
              <label>
                Name
                <input type="text" value={fields.name} onChange={(e) => setField('name', e.target.value)} readOnly={lookingUp} />
              </label>
              <label>
                City
                <input type="text" value={fields.city} onChange={(e) => setField('city', e.target.value)} readOnly={lookingUp} />
              </label>
              <label>
                Country
                <input type="text" value={fields.country} readOnly title="Set from the commercial country branch this airport belongs to" />
              </label>
            </div>
            {notFound && (
              <p className="add-airport-modal__hint">
                Airport not found for that code — you can still fill in the fields manually.
              </p>
            )}
          </section>

          {/* Cost Information + Other cost description/amount are hidden for FRESH24 —
              not part of that module's workflow — but the fields stay in `fields`
              state and the onSave payload below so this form is still complete for
              a future company that does need them; only the inputs are hidden. */}

          <section className="add-airport-modal__section">
            <h4>Additional &amp; Location Information</h4>
            <div className="add-airport-modal__grid">
              <label>
                Altitude (ft)
                <input type="text" value={fields.altitudeFt} readOnly placeholder="Auto from IATA code" />
              </label>
            </div>
          </section>

          <section className="add-airport-modal__section">
            <h4>Local Branch</h4>
            <div className="add-airport-modal__grid">
              <label>
                Local Branch Manager
                <input type="text" value={fields.branchManager} onChange={(e) => setField('branchManager', e.target.value)} />
              </label>
              <label>
                Local Branch User
                <input type="text" value={fields.branchUser} onChange={(e) => setField('branchUser', e.target.value)} />
              </label>
            </div>
          </section>

          {error && <div className="add-airport-modal__error">{error}</div>}

          <div className="add-airport-modal__actions">
            <button type="button" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" disabled={saving || lookingUp}>
              {saving ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Add Airport'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddAirportModal
