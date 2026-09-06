import { useEffect, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchExpenseCategories } from '../../../../../services/expenses'
import { CATEGORIES } from './categories'

function AddEntryModal({ category, initialDate, calendarMode, onSave, onCancel }) {
  const categoryMeta = CATEGORIES.find((item) => item.key === category)
  const [entryDate, setEntryDate] = useState(initialDate)
  const [description, setDescription] = useState('')
  const [entryType, setEntryType] = useState('')
  const [client, setClient] = useState('')
  const [amount, setAmount] = useState('')
  const [expenseCategories, setExpenseCategories] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (category !== 'expenses') return
    fetchExpenseCategories()
      .then(setExpenseCategories)
      .catch(() => setExpenseCategories([]))
  }, [category])

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
    if (category === 'expenses' && !description) {
      setError('Pick an expense category.')
      return
    }

    await onSave({
      category,
      entry_date: entryDate,
      description: category === 'revenue' ? null : description.trim() || null,
      entry_type: category === 'revenue' ? entryType.trim() || null : null,
      client: category === 'revenue' ? client.trim() || null : null,
      amount: parsedAmount,
    })
  }

  const dateField = (
    <label>
      Date
      {calendarMode === 'simulation' ? (
        <SimulationDatePicker value={entryDate} onChange={setEntryDate} />
      ) : (
        <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} aria-label="Entry date" />
      )}
    </label>
  )

  return (
    <div className="commercial-ops-modal__overlay" onClick={onCancel}>
      <div className="commercial-ops-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Add {categoryMeta?.label ?? 'entry'}</h3>
        <form className="commercial-ops-modal__form" onSubmit={handleSubmit}>
          {dateField}

          {category === 'revenue' && (
            <>
              <label>
                Type
                <input
                  type="text"
                  value={entryType}
                  onChange={(event) => setEntryType(event.target.value)}
                  placeholder="e.g. Product sale, Subscription"
                />
              </label>
              <label>
                Client
                <input
                  type="text"
                  value={client}
                  onChange={(event) => setClient(event.target.value)}
                  placeholder="e.g. Acme Corp"
                />
              </label>
            </>
          )}

          {category === 'expenses' && (
            <label>
              Description
              <select value={description} onChange={(event) => setDescription(event.target.value)}>
                <option value="">-- Select an expense category --</option>
                {expenseCategories.map((item) => (
                  <option key={item.id} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {category === 'cos' && (
            <label>
              Description (optional)
              <input
                type="text"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="e.g. Raw materials"
              />
            </label>
          )}

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
