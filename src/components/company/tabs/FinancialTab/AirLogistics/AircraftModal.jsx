import { useMemo, useState } from 'react'

const LB_PER_KG = 2.20462
const LB_PER_GAL_JET_A = 6.7 // approximate Jet-A density, as in the original module

// [field, label, unit, factor to lb, required]
const WEIGHTS = [
  ['mtow_kg', 'MTOW', 'kg', LB_PER_KG, true],
  ['mldgw_kg', 'Max landing weight', 'kg', LB_PER_KG, false],
  ['max_ramp_kg', 'Max ramp weight', 'kg', LB_PER_KG, false],
  ['empty_weight_kg', 'Empty weight', 'kg', LB_PER_KG, true],
  ['max_payload_kg', 'Max payload', 'kg', LB_PER_KG, true],
  ['zero_fuel_kg', 'Zero fuel weight', 'kg', LB_PER_KG, true],
]
const FUEL = [
  ['fuel_capacity_gal', 'Fuel capacity', 'gal', LB_PER_GAL_JET_A, true],
  ['fuel_burn_gal_hr', 'Fuel burn (per hour)', 'gal', LB_PER_GAL_JET_A, true],
  ['min_fuel_landed_gal', 'Min fuel landed', 'gal', LB_PER_GAL_JET_A, false],
  ['min_fuel_alternate_gal', 'Min fuel alternate', 'gal', LB_PER_GAL_JET_A, false],
]
const PAIRS = [...WEIGHTS, ...FUEL]

const round = (value, digits = 2) => (Number.isFinite(value) ? String(Math.round(value * 10 ** digits) / 10 ** digits) : '')
const num = (text) => (text === '' || text === undefined || text === null ? null : Number(text))

function initialState(aircraft) {
  const state = {
    manufacturer: aircraft?.manufacturer ?? '',
    model: aircraft?.model ?? '',
    short_name: aircraft?.short_name ?? '',
    cargo_positions_main_deck: aircraft?.cargo_positions_main_deck ?? '',
    cargo_positions_lower_deck: aircraft?.cargo_positions_lower_deck ?? '',
    cruise_speed_kt: aircraft?.cruise_speed_kt ?? '',
  }
  PAIRS.forEach(([field, , , factor]) => {
    const value = aircraft?.[field]
    state[field] = value ?? ''
    state[`${field}__lb`] = value != null ? round(value * factor) : ''
  })
  return state
}

// Ranges, as AI_FRESH24's aircraft form computed them (all in lb):
// at max payload = (MTOW − ZFW − min alternate − min landed) / burn × cruise;
// with max fuel = (capacity − min landed − min alternate) / burn × cruise.
function computeRanges(form) {
  const lb = (field) => (num(form[`${field}__lb`]) ?? 0)
  const burn = lb('fuel_burn_gal_hr')
  const cruise = num(form.cruise_speed_kt) ?? 0
  if (burn <= 0 || cruise <= 0) return { atMaxPayload: null, withMaxFuel: null }
  const reserve = lb('min_fuel_alternate_gal') + lb('min_fuel_landed_gal')
  const atMaxPayload = ((lb('mtow_kg') - lb('zero_fuel_kg') - reserve) / burn) * cruise
  const withMaxFuel = ((lb('fuel_capacity_gal') - reserve) / burn) * cruise
  return {
    atMaxPayload: atMaxPayload > 0 ? Math.round(atMaxPayload) : null,
    withMaxFuel: withMaxFuel > 0 ? Math.round(withMaxFuel) : null,
  }
}

function AircraftModal({ aircraft, onSave, onCancel }) {
  const [form, setForm] = useState(() => initialState(aircraft))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const ranges = useMemo(() => computeRanges(form), [form])

  const setField = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))
  // Editing either side of a pair updates the other, like the original form.
  const setPair = (field, factor, side) => (event) => {
    const text = event.target.value
    setForm((prev) =>
      side === 'base'
        ? { ...prev, [field]: text, [`${field}__lb`]: text === '' ? '' : round(Number(text) * factor) }
        : { ...prev, [`${field}__lb`]: text, [field]: text === '' ? '' : round(Number(text) / factor) },
    )
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const missing = [
      ['manufacturer', 'Manufacturer'],
      ['model', 'Model'],
      ['short_name', 'Short name'],
      ['cargo_positions_main_deck', 'Main deck positions'],
      ['cargo_positions_lower_deck', 'Lower deck positions'],
      ['cruise_speed_kt', 'Cruise speed'],
      ...PAIRS.filter(([, , , , required]) => required).map(([field, label]) => [field, label]),
    ].filter(([field]) => String(form[field]).trim() === '')
    if (missing.length) {
      setError(`Required: ${missing.map(([, label]) => label).join(', ')}.`)
      return
    }
    const payload = {
      manufacturer: form.manufacturer.trim(),
      model: form.model.trim(),
      short_name: form.short_name.trim(),
      cargo_positions_main_deck: Math.round(Number(form.cargo_positions_main_deck)),
      cargo_positions_lower_deck: Math.round(Number(form.cargo_positions_lower_deck)),
      cruise_speed_kt: Number(form.cruise_speed_kt),
      max_range_at_max_payload_nm: ranges.atMaxPayload,
      max_range_with_max_fuel_nm: ranges.withMaxFuel,
    }
    PAIRS.forEach(([field]) => {
      payload[field] = num(form[field])
    })
    if (Object.values(payload).some((value) => typeof value === 'number' && Number.isNaN(value))) {
      setError('Every numeric field must be a number.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave(payload)
    } catch (err) {
      setError(err.message || 'Could not save the aircraft.')
      setSaving(false)
    }
  }

  const pairInputs = (rows) =>
    rows.map(([field, label, unit, factor]) => (
      <label key={field}>
        {label}
        <div className="air-logistics-modal__pair">
          <input type="number" step="any" placeholder={unit} value={form[field]} onChange={setPair(field, factor, 'base')} />
          <input type="number" step="any" placeholder="lb" value={form[`${field}__lb`]} onChange={setPair(field, factor, 'lb')} />
        </div>
      </label>
    ))

  return (
    <div className="revenue-stream-modal__overlay">
      <div className="revenue-stream-modal air-logistics-modal">
        <h3>{aircraft ? 'Edit Aircraft' : 'Add Aircraft'}</h3>
        <p className="air-logistics-modal__hint">Enter weights in kg or lb and fuel in gallons or lb — the other unit fills in automatically.</p>
        <form className="revenue-stream-modal__form" onSubmit={handleSubmit}>
          <div className="air-logistics-modal__section-title">Basic information</div>
          <div className="air-logistics-modal__grid">
            <label>
              Manufacturer
              <input type="text" value={form.manufacturer} onChange={setField('manufacturer')} placeholder="e.g. Boeing" />
            </label>
            <label>
              Model
              <input type="text" value={form.model} onChange={setField('model')} placeholder="e.g. 737-400SF" />
            </label>
            <label>
              Short name
              <input type="text" value={form.short_name} onChange={setField('short_name')} placeholder="e.g. B734F" />
            </label>
          </div>

          <div className="air-logistics-modal__section-title">Weights (kg | lb)</div>
          <div className="air-logistics-modal__grid air-logistics-modal__grid--pairs">{pairInputs(WEIGHTS)}</div>

          <div className="air-logistics-modal__section-title">Fuel (gal | lb)</div>
          <div className="air-logistics-modal__grid air-logistics-modal__grid--pairs">{pairInputs(FUEL)}</div>

          <div className="air-logistics-modal__section-title">Operations</div>
          <div className="air-logistics-modal__grid">
            <label>
              Main deck positions
              <input type="number" step="1" min="0" value={form.cargo_positions_main_deck} onChange={setField('cargo_positions_main_deck')} />
            </label>
            <label>
              Lower deck positions
              <input type="number" step="1" min="0" value={form.cargo_positions_lower_deck} onChange={setField('cargo_positions_lower_deck')} />
            </label>
            <label>
              Cruise speed (kt)
              <input type="number" step="any" min="0" value={form.cruise_speed_kt} onChange={setField('cruise_speed_kt')} />
            </label>
            <label>
              Max range at max payload (nm)
              <input type="text" value={ranges.atMaxPayload ?? ''} placeholder="Calculated" readOnly />
            </label>
            <label>
              Max range with max fuel (nm)
              <input type="text" value={ranges.withMaxFuel ?? ''} placeholder="Calculated" readOnly />
            </label>
          </div>

          {error && <div className="revenue-stream-modal__error">{error}</div>}

          <div className="revenue-stream-modal__actions">
            <button type="button" className="revenue-stream-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="revenue-stream-modal__save" disabled={saving}>
              {saving ? 'Saving…' : aircraft ? 'Save Changes' : 'Add Aircraft'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AircraftModal
