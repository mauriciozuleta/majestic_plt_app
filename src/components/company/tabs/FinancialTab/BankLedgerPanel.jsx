import { useEffect, useMemo, useState } from 'react'
import { fetchBankTransactions } from '../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../utils/currencyFormat'
import DateFilter from '../../../shared/DateFilter/DateFilter'
import './BankLedgerPanel.css'

function BankLedgerPanel({ accountId, calendarMode = 'real' }) {
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dateFilterPrefix, setDateFilterPrefix] = useState('')

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

  if (loading) return null

  return (
    <div className="bank-ledger-panel">
      {error && <div className="bank-ledger-panel__error">{error}</div>}

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
                  return (
                  <tr key={transaction.id}>
                    <td className="bank-ledger-panel__cell">{transaction.entry_date}</td>
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
