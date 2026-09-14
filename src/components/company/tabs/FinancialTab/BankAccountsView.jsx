import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import { createBankAccount, createBankTransfer, deleteBankAccount, fetchBankAccounts } from '../../../../services/bankAccounts'
import { fetchSettings } from '../../../../services/settings'
import AddBankAccountModal from './AddBankAccountModal'
import BankLedgerPanel from './BankLedgerPanel'
import TransferFundsModal from './TransferFundsModal'
import { colorForBankAccount } from './bankAccountColors'
import './BankAccountsView.css'

const ACCOUNT_TYPE_LABELS = { main: 'Main', secondary: 'Secondary' }

function BankAccountsView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [transferModalOpen, setTransferModalOpen] = useState(false)
  const [expandedAccountId, setExpandedAccountId] = useState(null)
  const [ledgerRefreshKey, setLedgerRefreshKey] = useState(0)
  const [calendarMode, setCalendarMode] = useState('real')

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [nextAccounts, settings] = await Promise.all([fetchBankAccounts(companyId), fetchSettings()])
      setAccounts(nextAccounts)
      setCalendarMode(settings.calendar_mode ?? 'real')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId])

  const handleSave = async (payload) => {
    await createBankAccount(companyId, payload)
    setModalOpen(false)
    await reload()
  }

  const handleTransfer = async (payload) => {
    await createBankTransfer(payload)
    setTransferModalOpen(false)
    setLedgerRefreshKey((key) => key + 1)
  }

  const handleDelete = async (event, accountId) => {
    event.stopPropagation()
    if (!window.confirm('Delete this bank account?')) return
    try {
      await deleteBankAccount(accountId)
      await reload()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="panel-surface bank-accounts-view">
      <h3>Bank Accounts</h3>
      <p>Company bank accounts — this module will grow to cover transactions and reconciliation later.</p>
      <div className="bank-accounts-view__actions">
        <button type="button" className="bank-accounts-view__add-btn" onClick={() => setModalOpen(true)}>
          + Add Account
        </button>
        {accounts.length > 1 && (
          <button type="button" className="bank-accounts-view__transfer-btn" onClick={() => setTransferModalOpen(true)}>
            Inter-bank Transfer
          </button>
        )}
      </div>

      {error && <div className="bank-accounts-view__error">{error}</div>}

      {!loading && accounts.length > 0 && (
        <ul className="bank-accounts-view__list">
          {accounts.map((account) => {
            const isExpanded = expandedAccountId === account.id
            return (
              <li key={account.id} className="bank-accounts-view__group">
                <div
                  className={`bank-accounts-view__item ${isExpanded ? 'bank-accounts-view__item--expanded' : ''}`}
                  onClick={() => setExpandedAccountId(isExpanded ? null : account.id)}
                  title={isExpanded ? 'Collapse ledger' : 'Open ledger'}
                >
                  {isExpanded ? (
                    <IconChevronDown size={16} className="bank-accounts-view__chevron" />
                  ) : (
                    <IconChevronRight size={16} className="bank-accounts-view__chevron" />
                  )}
                  <span
                    className="bank-accounts-view__logo"
                    style={account.logo ? { backgroundImage: `url(${account.logo})` } : undefined}
                  >
                    {!account.logo && account.bank_name.slice(0, 2).toUpperCase()}
                  </span>
                  <span className="bank-accounts-view__item-details">
                    <span className="bank-accounts-view__item-name" style={{ color: colorForBankAccount(account.id) }}>
                      {account.account_name}
                    </span>
                    <span className="bank-accounts-view__item-meta">
                      {account.bank_name} · {account.account_number}
                    </span>
                  </span>
                  <span className={`bank-accounts-view__type-tag bank-accounts-view__type-tag--${account.account_type}`}>
                    {ACCOUNT_TYPE_LABELS[account.account_type] ?? account.account_type}
                  </span>
                  <button
                    type="button"
                    className="bank-accounts-view__remove"
                    title="Delete this account"
                    onClick={(event) => handleDelete(event, account.id)}
                  >
                    ×
                  </button>
                </div>
                {isExpanded && <BankLedgerPanel key={ledgerRefreshKey} accountId={account.id} calendarMode={calendarMode} />}
              </li>
            )
          })}
        </ul>
      )}

      {!loading && accounts.length === 0 && (
        <div className="bank-accounts-view__empty">No bank accounts yet.</div>
      )}

      {modalOpen && (
        <AddBankAccountModal existingAccounts={accounts} onSave={handleSave} onCancel={() => setModalOpen(false)} />
      )}

      {transferModalOpen && (
        <TransferFundsModal accounts={accounts} onSave={handleTransfer} onCancel={() => setTransferModalOpen(false)} />
      )}
    </div>
  )
}

export default BankAccountsView
