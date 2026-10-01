import { useState } from 'react'
import { branchLabel } from './branchLabel'

// Origin and destination are both chosen from the airports added as branches
// in the commercial structure; the destination list disables whichever
// branch is already the origin.
function AddRouteModal({ streamName, branches, onSave, onCancel }) {
  const [originId, setOriginId] = useState('')
  const [destinationId, setDestinationId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleOriginChange = (value) => {
    setOriginId(value)
    if (value && value === destinationId) setDestinationId('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!originId || !destinationId) {
      setError('Select both an origin and a destination.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave({ origin_branch_id: originId, destination_branch_id: destinationId })
    } catch (err) {
      setError(err.message || 'Could not save the route.')
    } finally {
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
            <select value={destinationId} onChange={(event) => setDestinationId(event.target.value)} disabled={!originId}>
              <option value="">Select an airport…</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id} disabled={branch.id === originId}>
                  {branchLabel(branch)}
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
            <button type="submit" className="revenue-stream-modal__save" disabled={saving || !originId || !destinationId}>
              {saving ? 'Saving…' : 'Save and Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddRouteModal
