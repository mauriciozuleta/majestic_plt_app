import { useMemo, useState } from 'react'
import { IconPaperclip } from '@tabler/icons-react'

function AddStartupRecordModal({ category, categoryLabel, monthCount, initialRecord, onSave, onCancel }) {
  const isEditing = Boolean(initialRecord)
  const [name, setName] = useState(initialRecord?.name ?? '')
  const [description, setDescription] = useState(initialRecord?.description ?? '')
  const [installments, setInstallments] = useState(() =>
    initialRecord ? initialRecord.months.map((value) => String(value)) : new Array(monthCount).fill(''),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const totalAmount = useMemo(
    () => installments.reduce((sum, value) => sum + (Number(value) || 0), 0),
    [installments],
  )

  const handleInstallmentChange = (index, value) => {
    setInstallments((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Name is required.')
      return
    }
    if (totalAmount <= 0) {
      setError('Enter at least one month value greater than 0.')
      return
    }

    setSaving(true)
    try {
      await onSave({
        category,
        name: name.trim(),
        description: description.trim() || null,
        total_amount: totalAmount,
        use_installments: true,
        months: installments.map((value) => Number(value) || 0),
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="startup-record-modal__overlay">
      <div className="startup-record-modal">
        <h3>{isEditing ? 'Edit record' : 'Add record'} — {categoryLabel}</h3>
        <form className="startup-record-modal__form" onSubmit={handleSubmit}>
          <label>
            Name
            <input type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Office lease deposit" />
          </label>

          <label>
            Description
            <input
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional details"
            />
          </label>

          <div className="startup-record-modal__installments">
            <div className="startup-record-modal__installments-grid">
              {installments.map((value, index) => (
                <label key={index} className="startup-record-modal__installment-cell">
                  M{index + 1}
                  <input
                    type="number"
                    step="0.01"
                    value={value}
                    onChange={(event) => handleInstallmentChange(index, event.target.value)}
                  />
                </label>
              ))}
            </div>
          </div>

          <label>
            Total amount
            <input type="text" value={`$${totalAmount.toLocaleString()}`} readOnly />
          </label>

          <div className="startup-record-modal__attach">
            <button type="button" className="startup-record-modal__attach-btn" title="Attach supporting documents (coming soon)" disabled>
              <IconPaperclip size={16} stroke={1.8} />
              Attach document
            </button>
          </div>

          {error && <div className="startup-record-modal__error">{error}</div>}

          <div className="startup-record-modal__actions">
            <button type="button" className="startup-record-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="startup-record-modal__save" disabled={saving}>
              {saving ? 'Saving…' : isEditing ? 'Save changes' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddStartupRecordModal
