import { useEffect, useMemo, useState } from 'react'
import SimulationDatePicker from '../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchSettings } from '../../../../services/settings'
import { getDefaultCalendarDate } from '../../../../services/calendarDates'
import { fetchBankTransactions } from '../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import { DAYS_1_TO_30, FREQUENCIES, MAX_OCCURRENCES, UNITS, buildRecurrenceDates } from '../OperationsTab/CommercialOperationsView/recurrence'
import './TransferFundsModal.css'

function accountLabel(account) {
  return `${account.bank_name} — ${account.account_name}`
}

function useAccountBalance(accountId) {
  const [balance, setBalance] = useState(null)

  useEffect(() => {
    if (!accountId) {
      setBalance(null)
      return undefined
    }
    let cancelled = false
    fetchBankTransactions(accountId)
      .then((transactions) => {
        if (cancelled) return
        setBalance(transactions.reduce((sum, transaction) => sum + transaction.credit - transaction.debit, 0))
      })
      .catch(() => {
        if (!cancelled) setBalance(null)
      })
    return () => {
      cancelled = true
    }
  }, [accountId])

  return balance
}

function TransferFundsModal({ accounts, onSave, onCancel }) {
  const [calendarMode, setCalendarMode] = useState('real')
  const [fromAccountId, setFromAccountId] = useState('')
  const [toAccountId, setToAccountId] = useState('')
  const [amount, setAmount] = useState('')
  const [entryDate, setEntryDate] = useState('')
  // Recurring transfer — e.g. "move $X into the reserve account every 30
  // days" — kept independent of any expense/COS entry, since setting money
  // aside is a balance-sheet-only move with no accrual or payment schedule
  // of its own attached to it. Same recurrence primitives as "Repeat this
  // entry" on Commercial Operations, minus anything settlement-related
  // (a transfer has no separate settlement leg to schedule).
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState('monthly')
  const [customUnit, setCustomUnit] = useState('day')
  const [repeatInterval, setRepeatInterval] = useState(1)
  const [recurrenceDay1, setRecurrenceDay1] = useState(1)
  const [recurrenceDay2, setRecurrenceDay2] = useState(15)
  const [untilDate, setUntilDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        const mode = settings.calendar_mode ?? 'real'
        setCalendarMode(mode)
        setEntryDate((prev) => prev || getDefaultCalendarDate(mode))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const fromBalance = useAccountBalance(fromAccountId)
  const toBalance = useAccountBalance(toAccountId)

  const renderDateInput = (value, onChange, ariaLabel) =>
    calendarMode === 'simulation' ? (
      <SimulationDatePicker value={value} onChange={onChange} />
    ) : (
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} aria-label={ariaLabel} />
    )

  const frequencyMeta = FREQUENCIES.find((item) => item.key === frequency)
  const effectiveUnit = frequency === 'custom' ? customUnit : frequencyMeta?.unit
  const unitLabel = effectiveUnit ? `${effectiveUnit}${Number(repeatInterval) === 1 ? '' : 's'}` : ''
  const occurrenceCount = useMemo(() => {
    if (!repeat || !entryDate || !untilDate) return 0
    return buildRecurrenceDates(calendarMode, entryDate, {
      frequency,
      customUnit,
      interval: repeatInterval,
      untilIsoDate: untilDate,
      biweeklyDays: [Number(recurrenceDay1), Number(recurrenceDay2)],
    }).length
  }, [repeat, entryDate, untilDate, calendarMode, frequency, customUnit, repeatInterval, recurrenceDay1, recurrenceDay2])

  const handleSubmit = async (event) => {
    event.preventDefault()
    const parsedAmount = Number(amount)
    if (!fromAccountId || !toAccountId) {
      setError('Pick both an origin and a destination account.')
      return
    }
    if (fromAccountId === toAccountId) {
      setError('Choose two different accounts.')
      return
    }
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError('Amount must be greater than 0.')
      return
    }
    if (!entryDate) {
      setError('Date is required.')
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
      ? buildRecurrenceDates(calendarMode, entryDate, {
          frequency,
          customUnit,
          interval: repeatInterval,
          untilIsoDate: untilDate,
          biweeklyDays: [Number(recurrenceDay1), Number(recurrenceDay2)],
        })
      : [entryDate]

    setSaving(true)
    setError('')
    try {
      await onSave(
        dates.map((occurrenceEntryDate) => ({
          from_account_id: fromAccountId,
          to_account_id: toAccountId,
          amount: parsedAmount,
          entry_date: occurrenceEntryDate,
        })),
      )
    } catch (err) {
      setError(err.message || 'Could not create the transfer.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="transfer-funds-modal__overlay" onClick={onCancel}>
      <div className="transfer-funds-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Inter-bank Transfer</h3>
        <form className="transfer-funds-modal__form" onSubmit={handleSubmit}>
          <label>
            From Account
            <select value={fromAccountId} onChange={(event) => setFromAccountId(event.target.value)}>
              <option value="">-- Select an account --</option>
              {accounts
                .filter((account) => account.id !== toAccountId)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {accountLabel(account)}
                  </option>
                ))}
            </select>
            {fromAccountId && (
              <span className="transfer-funds-modal__balance">
                {fromBalance === null ? 'Loading…' : `Balance: ${formatCurrencyValue(fromBalance, 'USD')}`}
              </span>
            )}
          </label>

          <label>
            To Account
            <select value={toAccountId} onChange={(event) => setToAccountId(event.target.value)}>
              <option value="">-- Select an account --</option>
              {accounts
                .filter((account) => account.id !== fromAccountId)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {accountLabel(account)}
                    {account.is_reserve ? ' (Reserve)' : ''}
                  </option>
                ))}
            </select>
            {toAccountId && (
              <span className="transfer-funds-modal__balance">
                {toBalance === null ? 'Loading…' : `Balance: ${formatCurrencyValue(toBalance, 'USD')}`}
              </span>
            )}
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

          <label>
            Date
            {renderDateInput(entryDate, setEntryDate, 'Entry date')}
          </label>

          <label className="transfer-funds-modal__checkbox">
            <input type="checkbox" checked={repeat} onChange={(event) => setRepeat(event.target.checked)} />
            Repeat this transfer
          </label>

          {repeat && (
            <div className="transfer-funds-modal__repeat">
              <div className="transfer-funds-modal__repeat-row">
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
                {frequency === 'biweekly' ? (
                  <>
                    <label>
                      Day 1
                      <select value={recurrenceDay1} onChange={(event) => setRecurrenceDay1(Number(event.target.value))}>
                        {DAYS_1_TO_30.map((day) => (
                          <option key={day} value={day}>
                            {day}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Day 2
                      <select value={recurrenceDay2} onChange={(event) => setRecurrenceDay2(Number(event.target.value))}>
                        {DAYS_1_TO_30.map((day) => (
                          <option key={day} value={day}>
                            {day}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                ) : (
                  <>
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
                      <span className="transfer-funds-modal__repeat-unit">{unitLabel}</span>
                    )}
                  </>
                )}
              </div>
              <label>
                Until
                {renderDateInput(untilDate, setUntilDate, 'Repeat until')}
              </label>
              {occurrenceCount > 0 && (
                <p className="transfer-funds-modal__repeat-hint">
                  This will create {occurrenceCount} {occurrenceCount === 1 ? 'transfer' : 'transfers'}
                  {occurrenceCount >= MAX_OCCURRENCES ? ` (capped at ${MAX_OCCURRENCES})` : ''}.
                </p>
              )}
            </div>
          )}

          {error && <div className="transfer-funds-modal__error">{error}</div>}

          <div className="transfer-funds-modal__actions">
            <button type="button" className="transfer-funds-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="transfer-funds-modal__save" disabled={saving}>
              {saving ? 'Transferring…' : 'Transfer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default TransferFundsModal
