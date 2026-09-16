import { useState } from 'react'
import './RiskAnalysisView.css'

// Captures a new risk or mechanism's name + description first — the
// description is what Generate Plan later reads from, so it's worth a
// deliberate moment before the scoring dropdowns even show up on the card.
function RiskEntryModal({ kind, onSave, onCancel }) {
  const isRisk = kind === 'risk'
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const handleSave = () => {
    const trimmedName = name.trim()
    if (!trimmedName) {
      setError(`${isRisk ? 'Risk' : 'Mechanism'} name is required.`)
      return
    }
    onSave({ name: trimmedName, description: description.trim() })
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3 style={{ color: isRisk ? 'var(--risk-color)' : 'var(--mech-color)' }}>
          {isRisk ? 'New risk' : 'New management mechanism'}
        </h3>
        <p className="modal-sub">Scoring dropdowns appear on the card once this is saved.</p>
        <label>
          {isRisk ? 'Risk' : 'Mechanism'} name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={isRisk ? 'e.g. Inability to get the required aircraft' : 'e.g. Dual-source aircraft leasing'}
            autoFocus
          />
        </label>
        <label>
          {isRisk ? "Danger — what happens if this isn't managed" : 'Description — how it works / why it helps'}
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={
              isRisk
                ? 'e.g. Certification process cannot be achieved; intercompany operations will be delayed, resulting in higher logistics costs.'
                : 'e.g. Pre-negotiated backup lease with a second operator, exercisable within 30 days if the primary aircraft is delayed.'
            }
          />
        </label>
        {error && <div className="modal-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn modal-save" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

export default RiskEntryModal
