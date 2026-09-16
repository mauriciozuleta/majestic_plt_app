import { useEffect, useMemo, useState } from 'react'
import { fetchBankTransactions } from '../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import { getDefaultCalendarDate } from '../../../../services/calendarDates'
import SimulationDatePicker from '../../../shared/SimulationCalendar/SimulationDatePicker'
import DateFilter from '../../../shared/DateFilter/DateFilter'
import './BankLedgerPanel.css'

function BankLedgerPanel({ accountId, calendarMode = 'real' }) {
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dateFilterPrefix, setDateFilterPrefix] = useState('')
  // Reference date for the "committed vs free" breakdown below — separate
  // from dateFilterPrefix, which only controls which ledger rows are
  // visible and has no "as of" meaning of its own (it's a prefix match, not
  // a cutoff).
  const [referenceDate, setReferenceDate] = useState(() => getDefaultCalendarDate(calendarMode))

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    fetchBankTransactions(accountId)
      .then((rows) => {
        if (!cancelled) setTransactions(rows)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [accountId])

  // Transactions arrive oldest-first, which is what the running balance
  // needs to be computed correctly — that happens over the FULL history
  // first, so a date filter only changes which rows are visible, never what
  // balance they show. Newest-first for display happens last.
  const visibleRows = useMemo(() => {
    const rows = []
    for (const transaction of transactions) {
      const previousBalance = rows.length ? rows[rows.length - 1].balance : 0
      rows.push({ ...transaction, balance: previousBalance + transaction.credit - transaction.debit })
    }
    const filtered = dateFilterPrefix ? rows.filter((row) => row.entry_date.startsWith(dateFilterPrefix)) : rows
    return filtered.slice().reverse()
  }, [transactions, dateFilterPrefix])

  // "Committed" cash: a cos/expense transaction dated after the reference
  // date hasn't actually left the account as of that date, even though it's
  // already posted (this app posts a settlement-date disbursement the
  // moment the entry is saved, not when that date arrives) — so it's cash
  // that's already spoken for. Revenue credits and internal/reserve
  // transfers are never "committed" in this sense, hence the source_type
  // and debit>0 checks. A reserve-funded entry's future disbursement is
  // dated against the reserve account instead of this one (see
  // commercial_operations.py's _post_bank_transaction), so once reserve-
  // funded it correctly drops out of the ORIGINAL account's committed total
  // and shows up in the reserve account's own breakdown instead.
  //
  // On the RESERVE account itself, a pending disbursement must only count
  // once its own funding transfer has actually landed here — both legs
  // share source_id (see commercial_operations.py's _post_reserve_transfer).
  // If the funding transfer is also still in the future as of referenceDate,
  // that cycle hasn't touched this account's balance at all yet, so
  // flagging its future debit as "committed against the current balance"
  // would wrongly suggest the pre-funded reserve itself is what's paying for
  // it, when really next cycle's transfer from the source account is.
  const committed = useMemo(() => {
    const fundedSourceIds = new Set()
    transactions.forEach((transaction) => {
      if (transaction.source_type === 'commercial_operation_reserve_transfer' && transaction.credit > 0 && transaction.entry_date <= referenceDate) {
        fundedSourceIds.add(transaction.source_id)
      }
    })
    const hasReserveTransfer = new Set(
      transactions.filter((transaction) => transaction.source_type === 'commercial_operation_reserve_transfer').map((transaction) => transaction.source_id),
    )

    const buckets = new Map()
    let total = 0
    transactions.forEach((transaction) => {
      if (transaction.source_type !== 'commercial_operation_entry') return
      if (transaction.debit <= 0) return
      if (transaction.entry_date <= referenceDate) return
      if (hasReserveTransfer.has(transaction.source_id) && !fundedSourceIds.has(transaction.source_id)) return
      const label = transaction.description || 'Uncategorized'
      buckets.set(label, (buckets.get(label) || 0) + transaction.debit)
      total += transaction.debit
    })
    return { rows: [...buckets.entries()].sort((a, b) => b[1] - a[1]), total }
  }, [transactions, referenceDate])

  const balanceAsOf = useMemo(
    () => transactions.filter((transaction) => transaction.entry_date <= referenceDate).reduce((sum, transaction) => sum + transaction.credit - transaction.debit, 0),
    [transactions, referenceDate],
  )
  const freeBalance = balanceAsOf - committed.total

  if (loading) return null

  return (
    <div className="bank-ledger-panel">
      {error && <div className="bank-ledger-panel__error">{error}</div>}

      {!error && transactions.length > 0 && (
        <div className="bank-ledger-panel__commitments">
          <div className="bank-ledger-panel__commitments-header">
            <span>Committed vs. free, as of</span>
            {calendarMode === 'simulation' ? (
              <SimulationDatePicker value={referenceDate} onChange={setReferenceDate} />
            ) : (
              <input type="date" value={referenceDate} onChange={(event) => setReferenceDate(event.target.value)} />
            )}
          </div>
          <div className="bank-ledger-panel__commitments-summary">
            <span>
              Balance <strong>{formatCurrencyValue(balanceAsOf, 'USD')}</strong>
            </span>
            <span>
              Committed <strong>{formatCurrencyValue(committed.total, 'USD')}</strong>
            </span>
            <span>
              Free{' '}
              <strong className={freeBalance < 0 ? 'bank-ledger-panel__balance--negative' : 'bank-ledger-panel__balance--positive'}>
                {formatCurrencyValue(freeBalance, 'USD')}
              </strong>
            </span>
          </div>
          {committed.rows.length > 0 && (
            <ul className="bank-ledger-panel__commitments-list">
              {committed.rows.map(([label, amount]) => (
                <li key={label}>
                  <span>{label}</span>
                  <span>{formatCurrencyValue(amount, 'USD')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!error && transactions.length > 0 && (
        <DateFilter calendarMode={calendarMode} onChange={setDateFilterPrefix} />
      )}

      {!error && transactions.length === 0 && (
        <div className="bank-ledger-panel__empty">No transactions posted to this account yet.</div>
      )}

      {!error && transactions.length > 0 && visibleRows.length === 0 && (
        <div className="bank-ledger-panel__empty">No transactions match this date filter.</div>
      )}

      {!error && visibleRows.length > 0 && (
        <>
          <div className="bank-ledger-panel__scroll">
            <table className="bank-ledger-panel__table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Reference</th>
                  <th>Transaction</th>
                  <th>Origin/Beneficiary</th>
                  <th>Credit</th>
                  <th>Debit</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((transaction) => {
                  const counterpartyClass = transaction.credit > 0 ? 'bank-ledger-panel__credit' : 'bank-ledger-panel__debit'
                  // This ledger pre-generates every occurrence of a
                  // recurring entry up front, dated on its real future date
                  // — it doesn't wait for that date to arrive before
                  // posting it. Sorted newest-first, that means the rows a
                  // reader sees first are often the furthest in the future,
                  // which reads as "already spent" unless flagged.
                  // "Scheduled" marks anything not yet realized as of the
                  // Committed/Free panel's reference date above.
                  const isScheduled = transaction.entry_date > referenceDate
                  return (
                  <tr key={transaction.id} className={isScheduled ? 'bank-ledger-panel__row--scheduled' : undefined}>
                    <td className="bank-ledger-panel__cell">
                      {transaction.entry_date}
                      {isScheduled && <span className="bank-ledger-panel__scheduled-badge">Scheduled</span>}
                    </td>
                    <td className="bank-ledger-panel__cell">{transaction.reference || '—'}</td>
                    <td className="bank-ledger-panel__cell">{transaction.description || '—'}</td>
                    <td className={counterpartyClass}>{transaction.client || '—'}</td>
                    <td className="bank-ledger-panel__credit">
                      {transaction.credit > 0 ? formatCurrencyValue(transaction.credit, 'USD') : '—'}
                    </td>
                    <td className="bank-ledger-panel__debit">
                      {transaction.debit > 0 ? formatCurrencyValue(transaction.debit, 'USD') : '—'}
                    </td>
                    <td
                      className={
                        transaction.balance >= 0
                          ? 'bank-ledger-panel__balance--positive'
                          : 'bank-ledger-panel__balance--negative'
                      }
                    >
                      {formatCurrencyValue(transaction.balance, 'USD')}
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default BankLedgerPanel
