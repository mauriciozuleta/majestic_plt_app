import { useEffect, useRef, useState } from 'react'
import { IconEdit, IconUpload, IconX } from '@tabler/icons-react'
import { makeLogoPreview, openLogoPicker } from '../../../../utils/logoUpload'
import { normalizeBankName } from '../../../../services/bankAccounts'
import './AddBankAccountModal.css'

const ACCOUNT_TYPE_OPTIONS = [
  { value: 'main', label: 'Main' },
  { value: 'secondary', label: 'Secondary' },
]

function AddBankAccountModal({ existingAccounts, onSave, onCancel }) {
  const inputRef = useRef(null)
  const [bankName, setBankName] = useState('')
  const [accountNumber, setAccountNumber] = useState('')
  const [accountType, setAccountType] = useState('main')
  const [accountName, setAccountName] = useState('')
  const [accountNameTouched, setAccountNameTouched] = useState(false)
  const [logo, setLogo] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  // Auto-fill "{Bank Name} Main Account" while the user hasn't typed their
  // own account name yet — the moment they edit it directly, it stops
  // following the bank name/type so their wording is never clobbered.
  useEffect(() => {
    if (accountNameTouched) return
    if (accountType === 'main') {
      setAccountName(bankName.trim() ? `${bankName.trim()} Main Account` : '')
    } else {
      setAccountName('')
    }
  }, [bankName, accountType, accountNameTouched])

  const handleSelectLogo = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const preview = await makeLogoPreview(file)
    setLogo(preview)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const trimmedBankName = bankName.trim()
    const trimmedAccountNumber = accountNumber.trim()
    const trimmedAccountName = accountName.trim()

    if (!trimmedBankName) {
      setError('Bank name is required.')
      return
    }
    if (!trimmedAccountNumber) {
      setError('Account number is required.')
      return
    }
    if (!trimmedAccountName) {
      setError('Account name is required.')
      return
    }
    if (
      accountType === 'main' &&
      existingAccounts.some(
        (account) => account.account_type === 'main' && normalizeBankName(account.bank_name) === normalizeBankName(trimmedBankName),
      )
    ) {
      setError(`"${trimmedBankName}" already has a Main account — only one is allowed per bank.`)
      return
    }

    setError('')
    setSaving(true)
    try {
      await onSave({
        bank_name: trimmedBankName,
        account_number: trimmedAccountNumber,
        account_type: accountType,
        account_name: trimmedAccountName,
        logo: logo || null,
      })
    } catch (saveError) {
      setError(saveError.message || 'Failed to save the account.')
      setSaving(false)
    }
  }

  return (
    <div className="bank-account-modal__overlay" onClick={onCancel}>
      <div className="bank-account-modal" onClick={(event) => event.stopPropagation()}>
        <div className="bank-account-modal__header">
          <h3>Add bank account</h3>
          <button type="button" className="bank-account-modal__close" onClick={onCancel} aria-label="Close modal">
            <IconX size={16} stroke={1.8} />
          </button>
        </div>

        <form className="bank-account-modal__form" onSubmit={handleSubmit}>
          <label className="bank-account-modal__field">
            Name of bank
            <input
              type="text"
              value={bankName}
              onChange={(event) => setBankName(event.target.value)}
              placeholder="Bank of America"
            />
          </label>

          <label className="bank-account-modal__field">
            Account number
            <input
              type="text"
              value={accountNumber}
              onChange={(event) => setAccountNumber(event.target.value)}
              placeholder="000123456789"
            />
          </label>

          <label className="bank-account-modal__field">
            Type of account
            <select value={accountType} onChange={(event) => setAccountType(event.target.value)}>
              {ACCOUNT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="bank-account-modal__field">
            Account name
            <input
              type="text"
              value={accountName}
              onChange={(event) => {
                setAccountName(event.target.value)
                setAccountNameTouched(true)
              }}
              placeholder="e.g. Bank of America Main Account"
            />
          </label>

          <div className="bank-account-modal__field">
            <label>Bank logo</label>
            <div className="bank-account-modal__upload-row">
              <button type="button" className="bank-account-modal__upload" onClick={() => openLogoPicker(inputRef)}>
                <IconUpload size={16} stroke={1.8} />
                Upload logo
              </button>
              {logo && (
                <button
                  type="button"
                  className="bank-account-modal__preview-card"
                  onClick={() => openLogoPicker(inputRef)}
                  aria-label="Edit bank logo"
                  title="Edit logo"
                >
                  <img src={logo} alt="Bank logo preview" className="bank-account-modal__preview" />
                  <span className="bank-account-modal__preview-edit">
                    <IconEdit size={13} stroke={2} />
                  </span>
                </button>
              )}
            </div>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="bank-account-modal__file-input"
              onChange={handleSelectLogo}
            />
          </div>

          {error && <div className="bank-account-modal__error">{error}</div>}

          <div className="bank-account-modal__actions">
            <button type="button" className="bank-account-modal__cancel" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="bank-account-modal__save" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddBankAccountModal
