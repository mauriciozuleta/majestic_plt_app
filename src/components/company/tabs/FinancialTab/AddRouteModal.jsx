import { useMemo, useState } from 'react'
import { aircraftLabel, branchLabel } from './branchLabel'

// Origin and destination are both chosen from the airports added as branches
// in the commercial structure (the destination list disables whichever
// branch is the origin). The provider comes from Providers ▸ Air Logistics;
// a provider with several aircraft has one record per aircraft, so choosing
// the provider by name and then one of its aircraft picks that record.
function AddRouteModal({ streamName, branches, providers, aircraftById, initialRoute, onSave, onCancel }) {
  const initialProvider = initialRoute ? providers.find((item) => item.id === initialRoute.charter_provider_id) : null
  const [originId, setOriginId] = useState(initialRoute?.origin_branch_id ?? '')
  const [destinationId, setDestinationId] = useState(initialRoute?.destination_branch_id ?? '')
  const [returnId, setReturnId] = useState(initialRoute?.return_branch_id ?? '')
  const [providerName, setProviderName] = useState(initialProvider?.name ?? '')
  const [providerRecordId, setProviderRecordId] = useState(initialProvider?.id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const providerNames = useMemo(() => [...new Set(providers.map((item) => item.name))].sort((a, b) => a.localeCompare(b)), [providers])
  const providerAircraft = useMemo(() => providers.filter((item) => item.name === providerName), [providers, providerName])

  const handleOriginChange = (value) => {
    setOriginId(value)
    if (value && value === destinationId) setDestinationId('')
  }

  // The return airport can be the origin (a round trip) but never the destination.
  const handleDestinationChange = (value) => {
    setDestinationId(value)
    if (value && value === returnId) setReturnId('')
  }

  const handleProviderChange = (value) => {
    setProviderName(value)
    const records = providers.filter((item) => item.name === value)
    // A provider with a single aircraft needs no second choice.
    setProviderRecordId(records.length === 1 ? records[0].id : '')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const record = providers.find((item) => item.id === providerRecordId)
    if (!originId || !destinationId || !returnId || !record) {
      setError('Select an origin, a destination, a return airport, a provider and an aircraft.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave({
        origin_branch_id: originId,
        destination_branch_id: destinationId,
        return_branch_id: returnId,
        charter_provider_id: record.id,
        aircraft_id: record.aircraft_id,
      })
    } catch (err) {
      setError(err.message || 'Could not save the route.')
      setSaving(false)
    }
  }

  return (
    <div className="revenue-stream-modal__overlay">
      <div className="revenue-stream-modal">
        <h3>{streamName}</h3>
        <form className="revenue-stream-modal__form" onSubmit={handleSubmit}>
          <label>
            Select origin
            <select value={originId} onChange={(event) => handleOriginChange(event.target.value)}>
              <option value="">Select an airport…</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branchLabel(branch)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Select destination
            <select value={destinationId} onChange={(event) => handleDestinationChange(event.target.value)} disabled={!originId}>
              <option value="">Select an airport…</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id} disabled={branch.id === originId}>
                  {branchLabel(branch)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Select return
            <select value={returnId} onChange={(event) => setReturnId(event.target.value)} disabled={!destinationId}>
              <option value="">Select an airport…</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id} disabled={branch.id === destinationId}>
                  {branchLabel(branch)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Select air logistic provider
            <select value={providerName} onChange={(event) => handleProviderChange(event.target.value)} disabled={providerNames.length === 0}>
              <option value="">{providerNames.length ? 'Select a provider…' : 'No providers in Providers ▸ Air Logistics yet'}</option>
              {providerNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Select aircraft
            <select value={providerRecordId} onChange={(event) => setProviderRecordId(event.target.value)} disabled={!providerName}>
              <option value="">Select an aircraft…</option>
              {providerAircraft.map((item) => (
                <option key={item.id} value={item.id}>
                  {aircraftLabel(aircraftById.get(item.aircraft_id)) ?? 'Aircraft no longer in the catalogue'}
                </option>
              ))}
            </select>
          </label>

          {branches.length === 0 && (
            <div className="revenue-stream-modal__error">No airports have been added as branches in the commercial structure yet.</div>
          )}
          {error && <div className="revenue-stream-modal__error">{error}</div>}

          <div className="revenue-stream-modal__actions">
            <button type="button" className="revenue-stream-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="revenue-stream-modal__save" disabled={saving || !originId || !destinationId || !returnId || !providerRecordId}>
              {saving ? 'Saving…' : initialRoute ? 'Save Changes' : 'Save and Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddRouteModal
