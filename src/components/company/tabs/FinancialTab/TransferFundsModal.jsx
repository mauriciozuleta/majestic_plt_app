import { useEffect, useState } from 'react'
import SimulationDatePicker from '../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchSettings } from '../../../../services/settings'
import { getDefaultCalendarDate } from '../../../../services/calendarDates'
import { fetchBankTransactions } from '../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
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

    setSaving(true)
    setError('')
    try {
      await onSave({ from_account_id: fromAccountId, to_account_id: toAccountId, amount: parsedAmount, entry_date: entryDate })
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
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={entryDate} onChange={setEntryDate} />
            ) : (
              <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
            )}
          </label>

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
