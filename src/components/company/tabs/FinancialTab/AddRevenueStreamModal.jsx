import { useState } from 'react'

function AddRevenueStreamModal({ onSave, onCancel }) {
  const [revenueType, setRevenueType] = useState('main')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Name is required.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await onSave({ revenue_type: revenueType, name: name.trim() })
    } catch (err) {
      setError(err.message || 'Could not save the revenue stream.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="revenue-stream-modal__overlay">
      <div className="revenue-stream-modal">
        <h3>Add Revenue Stream</h3>
        <form className="revenue-stream-modal__form" onSubmit={handleSubmit}>
          <label>
            Revenue Type
            <select value={revenueType} onChange={(event) => setRevenueType(event.target.value)}>
              <option value="main">Main</option>
              <option value="secondary">Secondary</option>
            </select>
          </label>
          <label>
            Name
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Charter Cargo Services"
            />
          </label>

          {error && <div className="revenue-stream-modal__error">{error}</div>}

          <div className="revenue-stream-modal__actions">
            <button type="button" className="revenue-stream-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="revenue-stream-modal__save" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddRevenueStreamModal
