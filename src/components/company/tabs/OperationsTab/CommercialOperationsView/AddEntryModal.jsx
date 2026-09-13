import { useEffect, useMemo, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchExpenseCategories } from '../../../../../services/expenses'
import { fetchBankAccounts, fetchBankTransactions, normalizeBankName } from '../../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { CATEGORIES } from './categories'
import { FREQUENCIES, MAX_OCCURRENCES, UNITS, buildRecurrenceDates } from './recurrence'
import { REVENUE_FLAGS, getTreatmentsForCategory } from './accountingTreatments'

function AddEntryModal({ companyId, category, initialDate, calendarMode, initialEntry, initialIsSimParameter, onSave, onCancel }) {
  const isEditMode = Boolean(initialEntry)
  const categoryMeta = CATEGORIES.find((item) => item.key === category)
  const treatments = getTreatmentsForCategory(category)
  const [entryDate, setEntryDate] = useState(initialEntry?.entry_date ?? initialDate)
  const [description, setDescription] = useState(initialEntry?.description ?? '')
  const [entryType, setEntryType] = useState(initialEntry?.entry_type ?? '')
  const [client, setClient] = useState(initialEntry?.client ?? '')
  const [referenceDocument, setReferenceDocument] = useState(initialEntry?.reference_document ?? '')
  const [paidTo, setPaidTo] = useState(initialEntry?.paid_to ?? '')
  const [amount, setAmount] = useState(initialEntry ? String(initialEntry.amount) : '')
  const [expenseCategories, setExpenseCategories] = useState([])
  const [bankAccounts, setBankAccounts] = useState([])
  const [selectedBankName, setSelectedBankName] = useState('')
  const [selectedAccountId, setSelectedAccountId] = useState('')
  const [selectedAccountBalance, setSelectedAccountBalance] = useState(null)
  const [accountingTreatment, setAccountingTreatment] = useState(initialEntry?.accounting_treatment ?? treatments[0]?.key ?? '')
  const [isDiscount, setIsDiscount] = useState(initialEntry?.is_discount ?? false)
  const [settlementDate, setSettlementDate] = useState(initialEntry?.settlement_date ?? '')
  // repeat itself always starts unchecked, even when editing an entry that
  // was originally created with a pattern — resaving without touching it
  // must never silently spawn a fresh batch of entries. The pattern fields
  // are still pre-filled from the entry so that if the user DOES check the
  // box to continue/change it, they start from what was actually used
  // rather than the generic defaults.
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState(initialEntry?.recurrence_frequency ?? 'weekly')
  const [customUnit, setCustomUnit] = useState(initialEntry?.recurrence_custom_unit ?? 'day')
  const [repeatInterval, setRepeatInterval] = useState(initialEntry?.recurrence_interval ?? 1)
  const [untilDate, setUntilDate] = useState(initialEntry?.recurrence_until_date ?? '')
  const [isSimParameter, setIsSimParameter] = useState(initialIsSimParameter ?? false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (category !== 'expenses') return
    fetchExpenseCategories()
      .then(setExpenseCategories)
      .catch(() => setExpenseCategories([]))
  }, [category])

  useEffect(() => {
    if (!companyId) return
    fetchBankAccounts(companyId)
      .then(setBankAccounts)
      .catch(() => setBankAccounts([]))
  }, [companyId])

  // Grouped by normalized bank name rather than exact string match — the
  // same bank can end up stored under slightly different casing/spacing
  // across accounts since bank name is free-typed, and without this an
  // account could silently disappear into a second "bank" entry instead of
  // showing up alongside its siblings.
  const bankNames = useMemo(() => {
    const seen = new Map()
    bankAccounts.forEach((account) => {
      const key = normalizeBankName(account.bank_name)
      if (!seen.has(key)) seen.set(key, account.bank_name)
    })
    return [...seen.values()]
  }, [bankAccounts])
  const accountsForSelectedBank = useMemo(
    () => bankAccounts.filter((account) => normalizeBankName(account.bank_name) === normalizeBankName(selectedBankName)),
    [bankAccounts, selectedBankName],
  )

  // Editing an existing entry: once accounts load, pre-select the bank and
  // account it was originally posted to (only the account id is stored on
  // the entry, so the matching bank name has to be looked up here). Must
  // resolve to whatever string actually appears in `bankNames` — the
  // account's own raw bank_name can differ in casing/spacing from the
  // deduped option list, which would leave the <select> unable to match any
  // of its own <option> values and appear to show nothing selected.
  useEffect(() => {
    if (!initialEntry?.bank_account_id || selectedBankName || bankAccounts.length === 0) return
    const match = bankAccounts.find((account) => account.id === initialEntry.bank_account_id)
    if (!match) return
    const canonicalBankName = bankNames.find((name) => normalizeBankName(name) === normalizeBankName(match.bank_name))
    setSelectedBankName(canonicalBankName ?? match.bank_name)
    setSelectedAccountId(match.id)
  }, [initialEntry, bankAccounts, bankNames, selectedBankName])
  const isDebitCategory = category === 'cos' || category === 'expenses'

  // Shows the account's current balance so the user can tell whether the
  // source they're about to pick actually has money for this cos/expense —
  // not shown for revenue, which is money coming in rather than out.
  useEffect(() => {
    if (!isDebitCategory || !selectedAccountId) {
      setSelectedAccountBalance(null)
      return undefined
    }
    let cancelled = false
    fetchBankTransactions(selectedAccountId)
      .then((transactions) => {
        if (cancelled) return
        setSelectedAccountBalance(transactions.reduce((sum, transaction) => sum + transaction.credit - transaction.debit, 0))
      })
      .catch(() => {
        if (!cancelled) setSelectedAccountBalance(null)
      })
    return () => {
      cancelled = true
    }
  }, [isDebitCategory, selectedAccountId])

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
    if (!selectedAccountId) {
      setError('Pick a bank account.')
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

    // If the box isn't checked, leave the entry's own recurrence memory
    // alone when editing (so it keeps showing what it was actually created
    // with) instead of wiping it just because this save didn't touch it.
    const recurrenceFields = repeat
      ? {
          recurrence_frequency: frequency,
          recurrence_interval: Number(repeatInterval) || 1,
          recurrence_custom_unit: frequency === 'custom' ? customUnit : null,
          recurrence_until_date: untilDate,
        }
      : {
          recurrence_frequency: initialEntry?.recurrence_frequency ?? null,
          recurrence_interval: initialEntry?.recurrence_interval ?? null,
          recurrence_custom_unit: initialEntry?.recurrence_custom_unit ?? null,
          recurrence_until_date: initialEntry?.recurrence_until_date ?? null,
        }

    const basePayload = {
      category,
      description: category === 'revenue' ? null : description.trim() || null,
      entry_type: category === 'revenue' ? entryType.trim() || null : null,
      client: category === 'revenue' ? client.trim() || null : null,
      amount: parsedAmount,
      accounting_treatment: accountingTreatment || null,
      is_discount: category === 'revenue' ? isDiscount : false,
      settlement_date: settlementDate || null,
      bank_account_id: selectedAccountId,
      reference_document: referenceDocument.trim() || null,
      paid_to: isDebitCategory ? paidTo.trim() || null : null,
      is_sim_parameter: isSimParameter,
      ...recurrenceFields,
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

  // Shown regardless of whether "Repeat this entry" is checked, so editing
  // an entry immediately reveals the pattern it was saved with — checking
  // the box only becomes necessary to actually change it or add more.
  const savedRecurrenceLabel = (() => {
    if (!isEditMode || !initialEntry?.recurrence_frequency) return null
    const savedFrequencyMeta = FREQUENCIES.find((item) => item.key === initialEntry.recurrence_frequency)
    const savedUnit = initialEntry.recurrence_frequency === 'custom' ? initialEntry.recurrence_custom_unit : savedFrequencyMeta?.unit
    const savedUnitLabel = UNITS.find((item) => item.key === savedUnit)?.label ?? savedUnit
    const savedInterval = initialEntry.recurrence_interval ?? 1
    const parts = [savedFrequencyMeta?.label ?? initialEntry.recurrence_frequency]
    if (savedInterval > 1) parts.push(`every ${savedInterval} ${savedUnitLabel}`)
    if (initialEntry.recurrence_until_date) parts.push(`until ${initialEntry.recurrence_until_date}`)
    return parts.join(', ')
  })()

  return (
    <div className="commercial-ops-modal__overlay" onClick={onCancel}>
      <div className="commercial-ops-modal" onClick={(event) => event.stopPropagation()}>
        <h3>{isEditMode ? 'Edit' : 'Add'} {categoryMeta?.label ?? 'entry'}</h3>
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

          <label>
            Reference Document
            <input
              type="text"
              value={referenceDocument}
              onChange={(event) => setReferenceDocument(event.target.value)}
              placeholder="e.g. Invoice #, PO #, receipt #"
            />
          </label>

          {isDebitCategory && (
            <label>
              Paid To
              <input
                type="text"
                value={paidTo}
                onChange={(event) => setPaidTo(event.target.value)}
                placeholder="Who is receiving the payment"
              />
            </label>
          )}

          <label>
            Bank
            <select
              value={selectedBankName}
              onChange={(event) => {
                setSelectedBankName(event.target.value)
                setSelectedAccountId('')
              }}
            >
              <option value="">-- Select a bank --</option>
              {bankNames.map((bankName) => (
                <option key={bankName} value={bankName}>
                  {bankName}
                </option>
              ))}
            </select>
          </label>

          {selectedBankName && (
            <label>
              Account
              <select value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}>
                <option value="">-- Select an account --</option>
                {accountsForSelectedBank.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.account_name} · {account.account_number}
                  </option>
                ))}
              </select>
              {isDebitCategory && selectedAccountId && (
                <span
                  className={`commercial-ops-modal__account-balance ${
                    selectedAccountBalance !== null && Number(amount) > selectedAccountBalance
                      ? 'commercial-ops-modal__account-balance--low'
                      : ''
                  }`}
                >
                  {selectedAccountBalance === null
                    ? 'Loading balance…'
                    : `Current balance: ${formatCurrencyValue(selectedAccountBalance, 'USD')}`}
                </span>
              )}
            </label>
          )}
          {isDebitCategory && selectedAccountId && (
            <p className="commercial-ops-modal__repeat-hint">This will post a debit to the selected account.</p>
          )}
          {!isDebitCategory && selectedAccountId && (
            <p className="commercial-ops-modal__repeat-hint">This will post a credit to the selected account.</p>
          )}

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
                <input type="checkbox" checked={isDiscount} onChange={(event) => setIsDiscount(event.target.checked)} />
                {flag.label}
              </label>
            ))}

          <label className="commercial-ops-modal__checkbox">
            <input type="checkbox" checked={repeat} onChange={(event) => setRepeat(event.target.checked)} />
            Repeat this entry
          </label>
          {savedRecurrenceLabel && (
            <p className="commercial-ops-modal__repeat-hint">
              Saved pattern: {savedRecurrenceLabel}. Check "Repeat this entry" to continue or change it.
            </p>
          )}
          {isEditMode && repeat && (
            <p className="commercial-ops-modal__repeat-hint">
              This updates the entry you're editing and adds new entries for the additional occurrences below — it
              doesn't affect any entries already created from an earlier repeat.
            </p>
          )}

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
                  {isEditMode
                    ? `This updates the edited entry and creates ${occurrenceCount - 1} additional ${
                        occurrenceCount - 1 === 1 ? 'entry' : 'entries'
                      }`
                    : `This will create ${occurrenceCount} ${occurrenceCount === 1 ? 'entry' : 'entries'}`}
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
              {saving ? 'Saving…' : isEditMode ? 'Save changes' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddEntryModal
