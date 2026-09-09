import { useEffect, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchExpenseCategories } from '../../../../../services/expenses'
import { CATEGORIES } from './categories'
import { FREQUENCIES, MAX_OCCURRENCES, UNITS, buildRecurrenceDates } from './recurrence'
import { REVENUE_FLAGS, getTreatmentsForCategory } from './accountingTreatments'

function AddEntryModal({ category, initialDate, calendarMode, onSave, onCancel }) {
  const categoryMeta = CATEGORIES.find((item) => item.key === category)
  const treatments = getTreatmentsForCategory(category)
  const [entryDate, setEntryDate] = useState(initialDate)
  const [description, setDescription] = useState('')
  const [entryType, setEntryType] = useState('')
  const [client, setClient] = useState('')
  const [amount, setAmount] = useState('')
  const [expenseCategories, setExpenseCategories] = useState([])
  const [accountingTreatment, setAccountingTreatment] = useState(treatments[0]?.key ?? '')
  const [isRecurring, setIsRecurring] = useState(false)
  const [isDiscount, setIsDiscount] = useState(false)
  const [settlementDate, setSettlementDate] = useState('')
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState('weekly')
  const [customUnit, setCustomUnit] = useState('day')
  const [repeatInterval, setRepeatInterval] = useState(1)
  const [untilDate, setUntilDate] = useState('')
  const [isSimParameter, setIsSimParameter] = useState(false)
  const [saving, setSaving] = useState(false)
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
    if (repeat && !untilDate) {
      setError('Pick an end date for the repeat.')
      return
    }
    if (repeat && untilDate < entryDate) {
      setError('The repeat end date must be after the start date.')
      return
    }

    const dates = repeat
      ? buildRecurrenceDates(calendarMode, entryDate, { frequency, customUnit, interval: repeatInterval, untilIsoDate: untilDate })
      : [entryDate]

    const basePayload = {
      category,
      description: category === 'revenue' ? null : description.trim() || null,
      entry_type: category === 'revenue' ? entryType.trim() || null : null,
      client: category === 'revenue' ? client.trim() || null : null,
      amount: parsedAmount,
      accounting_treatment: accountingTreatment || null,
      is_recurring: category === 'revenue' ? isRecurring : false,
      is_discount: category === 'revenue' ? isDiscount : false,
      settlement_date: settlementDate || null,
      is_sim_parameter: isSimParameter,
    }

    setSaving(true)
    setError('')
    try {
      await onSave(dates.map((entry_date) => ({ ...basePayload, entry_date })))
    } catch (err) {
      setError(err.message || 'Could not save the entry.')
    } finally {
      setSaving(false)
    }
  }

  const renderDateInput = (value, onChange, ariaLabel) =>
    calendarMode === 'simulation' ? (
      <SimulationDatePicker value={value} onChange={onChange} />
    ) : (
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} aria-label={ariaLabel} />
    )

  const dateField = (
    <label>
      Date
      {renderDateInput(entryDate, setEntryDate, 'Entry date')}
    </label>
  )

  const selectedTreatment = treatments.find((item) => item.key === accountingTreatment)

  const frequencyMeta = FREQUENCIES.find((item) => item.key === frequency)
  const effectiveUnit = frequency === 'custom' ? customUnit : frequencyMeta?.unit
  const unitLabel = effectiveUnit ? `${effectiveUnit}${Number(repeatInterval) === 1 ? '' : 's'}` : ''
  const occurrenceCount = repeat && untilDate
    ? buildRecurrenceDates(calendarMode, entryDate, { frequency, customUnit, interval: repeatInterval, untilIsoDate: untilDate }).length
    : 0

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

          <div className="commercial-ops-modal__treatments">
            <span className="commercial-ops-modal__treatments-label">Accounting Treatment</span>
            {treatments.map((item) => (
              <label key={item.key} className="commercial-ops-modal__radio" title={item.description}>
                <input
                  type="radio"
                  name="accounting-treatment"
                  value={item.key}
                  checked={accountingTreatment === item.key}
                  onChange={(event) => setAccountingTreatment(event.target.value)}
                />
                {item.label}
              </label>
            ))}
          </div>

          {selectedTreatment?.settlementLabel && (
            <label>
              {selectedTreatment.settlementLabel}
              {renderDateInput(settlementDate, setSettlementDate, selectedTreatment.settlementLabel)}
            </label>
          )}

          {category === 'revenue' &&
            REVENUE_FLAGS.map((flag) => (
              <label key={flag.key} className="commercial-ops-modal__checkbox" title={flag.description}>
                <input
                  type="checkbox"
                  checked={flag.key === 'is_recurring' ? isRecurring : isDiscount}
                  onChange={(event) =>
                    flag.key === 'is_recurring'
                      ? setIsRecurring(event.target.checked)
                      : setIsDiscount(event.target.checked)
                  }
                />
                {flag.label}
              </label>
            ))}

          <label className="commercial-ops-modal__checkbox">
            <input type="checkbox" checked={repeat} onChange={(event) => setRepeat(event.target.checked)} />
            Repeat this entry
          </label>

          {repeat && (
            <div className="commercial-ops-modal__repeat">
              <div className="commercial-ops-modal__repeat-row">
                <label>
                  Frequency
                  <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
                    {FREQUENCIES.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Every
                  <input
                    type="number"
                    min="1"
                    max="52"
                    value={repeatInterval}
                    onChange={(event) => setRepeatInterval(event.target.value)}
                  />
                </label>
                {frequency === 'custom' ? (
                  <label>
                    Unit
                    <select value={customUnit} onChange={(event) => setCustomUnit(event.target.value)}>
                      {UNITS.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <span className="commercial-ops-modal__repeat-unit">{unitLabel}</span>
                )}
              </div>
              <label>
                Until
                {renderDateInput(untilDate, setUntilDate, 'Repeat until')}
              </label>
              {occurrenceCount > 0 && (
                <p className="commercial-ops-modal__repeat-hint">
                  This will create {occurrenceCount} {occurrenceCount === 1 ? 'entry' : 'entries'}
                  {occurrenceCount >= MAX_OCCURRENCES ? ` (capped at ${MAX_OCCURRENCES})` : ''}.
                </p>
              )}
            </div>
          )}

          <label className="commercial-ops-modal__checkbox">
            <input
              type="checkbox"
              checked={isSimParameter}
              onChange={(event) => setIsSimParameter(event.target.checked)}
            />
            Sim Parameter
          </label>
          {isSimParameter && (
            <p className="commercial-ops-modal__repeat-hint">
              Flags this value as a lever the simulation agent can adjust later.
            </p>
          )}

          {error && <div className="commercial-ops-modal__error">{error}</div>}

          <div className="commercial-ops-modal__actions">
            <button type="button" className="commercial-ops-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="commercial-ops-modal__save" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddEntryModal
