import { useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { CATEGORIES } from './categories'

function AddEntryModal({ category, initialDate, calendarMode, onSave, onCancel }) {
  const categoryMeta = CATEGORIES.find((item) => item.key === category)
  const [entryDate, setEntryDate] = useState(initialDate)
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    const parsedAmount = Number(amount)
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError('Amount must be greater than 0.')
      return
    }
    if (!entryDate) {
      setError('Date is required.')
      return
    }

    await onSave({
      category,
      entry_date: entryDate,
      description: description.trim() || null,
      amount: parsedAmount,
    })
  }

  return (
    <div className="commercial-ops-modal__overlay" onClick={onCancel}>
      <div className="commercial-ops-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Add {categoryMeta?.label ?? 'entry'}</h3>
        <form className="commercial-ops-modal__form" onSubmit={handleSubmit}>
          <label>
            Date
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={entryDate} onChange={setEntryDate} />
            ) : (
              <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} aria-label="Entry date" />
            )}
          </label>
          <label>
            Description (optional)
            <input
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="e.g. Invoice #204"
            />
          </label>
          <label>
            Amount
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
            />
          </label>

          {error && <div className="commercial-ops-modal__error">{error}</div>}

          <div className="commercial-ops-modal__actions">
            <button type="button" className="commercial-ops-modal__cancel" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="commercial-ops-modal__save">
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddEntryModal
