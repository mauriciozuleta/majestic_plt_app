import { useMemo, useState } from 'react'
import { IconPaperclip } from '@tabler/icons-react'

const AMOUNT_TOLERANCE = 0.01

function AddStartupRecordModal({ category, categoryLabel, monthCount, initialRecord, onSave, onCancel }) {
  const isEditing = Boolean(initialRecord)
  const [name, setName] = useState(initialRecord?.name ?? '')
  const [description, setDescription] = useState(initialRecord?.description ?? '')
  const [totalAmount, setTotalAmount] = useState(initialRecord ? String(initialRecord.total_amount) : '')
  const [useInstallments, setUseInstallments] = useState(initialRecord?.use_installments ?? false)
  const [installments, setInstallments] = useState(() =>
    initialRecord?.use_installments ? initialRecord.months.map((value) => String(value)) : new Array(monthCount).fill(''),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const installmentSum = useMemo(
    () => installments.reduce((sum, value) => sum + (Number(value) || 0), 0),
    [installments],
  )
  const parsedTotal = Number(totalAmount) || 0
  const installmentsMatch = Math.abs(installmentSum - parsedTotal) <= AMOUNT_TOLERANCE

  const handleInstallmentChange = (index, value) => {
    setInstallments((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })
  }

  const handleToggleInstallments = (event) => {
    setUseInstallments(event.target.checked)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Name is required.')
      return
    }
    if (!Number.isFinite(parsedTotal) || parsedTotal <= 0) {
      setError('Total amount must be greater than 0.')
      return
    }
    if (useInstallments && !installmentsMatch) {
      setError(`Installments must add up to the total amount (currently $${installmentSum.toLocaleString()}).`)
      return
    }

    setSaving(true)
    try {
      await onSave({
        category,
        name: name.trim(),
        description: description.trim() || null,
        total_amount: parsedTotal,
        use_installments: useInstallments,
        months: useInstallments ? installments.map((value) => Number(value) || 0) : undefined,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="startup-record-modal__overlay" onClick={onCancel}>
      <div className="startup-record-modal" onClick={(event) => event.stopPropagation()}>
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

          <label>
            Total amount
            <input
              type="number"
              min="0"
              step="0.01"
              value={totalAmount}
              onChange={(event) => setTotalAmount(event.target.value)}
              placeholder="0.00"
            />
          </label>

          <label className="startup-record-modal__checkbox">
            <input type="checkbox" checked={useInstallments} onChange={handleToggleInstallments} />
            Installments
          </label>

          {useInstallments && (
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
              <div className={`startup-record-modal__installment-sum ${installmentsMatch ? 'is-match' : 'is-mismatch'}`}>
                Installments total: ${installmentSum.toLocaleString()} {installmentsMatch ? '✓' : `(expected $${parsedTotal.toLocaleString()})`}
              </div>
            </div>
          )}

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
