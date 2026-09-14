import { useEffect, useMemo, useState } from 'react'
import SimulationDatePicker from '../../../../shared/SimulationCalendar/SimulationDatePicker'
import { fetchExpenseCategories } from '../../../../../services/expenses'
import { fetchBankAccounts, fetchBankTransactions, normalizeBankName } from '../../../../../services/bankAccounts'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { CATEGORIES } from './categories'
import { DAYS_1_TO_30, FREQUENCIES, MAX_OCCURRENCES, UNITS, buildRecurrenceDates, resolveNextPayday } from './recurrence'
import { shiftIsoDate } from './calendarViewMath'
import { REVENUE_FLAGS, getTreatmentsForCategory } from './accountingTreatments'

function daysBetweenIso(isoA, isoB) {
  const a = new Date(`${isoA}T00:00:00Z`)
  const b = new Date(`${isoB}T00:00:00Z`)
  return Math.round((b - a) / (1000 * 60 * 60 * 24))
}

function AddEntryModal({
  companyId,
  category,
  initialDate,
  calendarMode,
  initialEntry,
  initialIsSimParameter,
  seriesEntryCount,
  onSave,
  onCancel,
}) {
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
  // For a repeating entry, a single fixed settlement_date can't apply to
  // every occurrence the same way — "Same day" (the common case: paid the
  // moment it's incurred, e.g. a subscription auto-charged same-day every
  // cycle) makes each occurrence settle on its own entry_date; "Select
  // date" keeps whatever gap the user set between this entry's date and its
  // settlement date, and re-applies that same gap to every later occurrence.
  const [settlementScheduleMode, setSettlementScheduleMode] = useState(() => {
    if (!initialEntry?.settlement_date || initialEntry.settlement_date === initialEntry.entry_date) return 'sameDay'
    return 'custom'
  })
  // repeat itself always starts unchecked, even when editing an entry that
  // was originally created with a pattern — resaving without touching it
  // must never silently spawn a fresh batch of entries. The pattern fields
  // are still pre-filled from the entry so that if the user DOES check the
  // box to continue/change it, they start from what was actually used
  // rather than the generic defaults.
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState(initialEntry?.recurrence_frequency ?? 'weekly')
  const [customUnit, setCustomUnit] = useState(
    initialEntry?.recurrence_frequency === 'custom' ? (initialEntry?.recurrence_custom_unit ?? 'day') : 'day',
  )
  const [repeatInterval, setRepeatInterval] = useState(
    initialEntry?.recurrence_frequency === 'biweekly' ? 1 : (initialEntry?.recurrence_interval ?? 1),
  )
  const [untilDate, setUntilDate] = useState(initialEntry?.recurrence_until_date ?? '')
  // 'biweekly' has no interval/unit of its own — it's always 2 fixed
  // calendar days a month. There's no dedicated storage for those 2 days,
  // so they're reused from recurrence_interval/recurrence_custom_unit
  // (otherwise meaningless for this frequency) purely as a round-trip
  // convenience when re-opening an entry that was created this way.
  const [recurrenceDay1, setRecurrenceDay1] = useState(() =>
    initialEntry?.recurrence_frequency === 'biweekly' ? Number(initialEntry.recurrence_interval) || 1 : 1,
  )
  const [recurrenceDay2, setRecurrenceDay2] = useState(() =>
    initialEntry?.recurrence_frequency === 'biweekly' ? Number(initialEntry.recurrence_custom_unit) || 15 : 15,
  )
  // The Accrued payment schedule's own day-of-month picker(s) — independent
  // of recurrenceDay1/2 above, since an expense can be incurred on one
  // schedule and paid on a completely different one.
  const [paymentDay1, setPaymentDay1] = useState(1)
  const [paymentDay2, setPaymentDay2] = useState(15)
  const [cascadeToSeries, setCascadeToSeries] = useState(false)
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
    if (category === 'cos' && !description.trim()) {
      setError('Description is required.')
      return
    }
    if (category === 'expenses' && !entryType.trim()) {
      setError('Short description is required.')
      return
    }
    if (category === 'revenue' && !entryType.trim()) {
      setError('Type is required.')
      return
    }
    if (category === 'revenue' && !client.trim()) {
      setError('Client is required.')
      return
    }
    if (!referenceDocument.trim()) {
      setError('Reference document is required.')
      return
    }
    if (isDebitCategory && !paidTo.trim()) {
      setError('Paid To is required.')
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
    const usesDayOfMonthSchedule = repeat && (frequency === 'monthly' || frequency === 'biweekly')
    if (selectedTreatment?.settlementLabel && !repeat && !settlementDate) {
      setError(`${selectedTreatment.settlementLabel} is required.`)
      return
    }
    if (selectedTreatment?.settlementLabel && repeat && !usesDayOfMonthSchedule && settlementScheduleMode === 'custom' && !settlementDate) {
      setError(`${selectedTreatment.settlementLabel} is required.`)
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

    // If the box isn't checked, leave the entry's own recurrence memory
    // alone when editing (so it keeps showing what it was actually created
    // with) instead of wiping it just because this save didn't touch it.
    const recurrenceFields = repeat
      ? {
          recurrence_frequency: frequency,
          // 'biweekly' has no interval/unit of its own — these 2 columns are
          // reused to carry its 2 configured days instead, purely so
          // re-opening the entry can restore them (see the state init above).
          recurrence_interval: frequency === 'biweekly' ? Number(recurrenceDay1) || 1 : Number(repeatInterval) || 1,
          recurrence_custom_unit:
            frequency === 'biweekly' ? String(Number(recurrenceDay2) || 15) : frequency === 'custom' ? customUnit : null,
          recurrence_until_date: untilDate,
        }
      : {
          recurrence_frequency: initialEntry?.recurrence_frequency ?? null,
          recurrence_interval: initialEntry?.recurrence_interval ?? null,
          recurrence_custom_unit: initialEntry?.recurrence_custom_unit ?? null,
          recurrence_until_date: initialEntry?.recurrence_until_date ?? null,
        }

    // A brand-new repeating batch (or an entry that's being linked into a
    // series for the first time by checking Repeat now) mints one id shared
    // by every row created together; an entry already in a series keeps its
    // id regardless of whether Repeat is checked this time.
    const seriesId = repeat && !initialEntry?.series_id ? crypto.randomUUID() : (initialEntry?.series_id ?? null)

    const basePayload = {
      category,
      description: category === 'revenue' ? null : description.trim() || null,
      entry_type: category === 'revenue' || category === 'expenses' ? entryType.trim() || null : null,
      client: category === 'revenue' ? client.trim() || null : null,
      amount: parsedAmount,
      accounting_treatment: accountingTreatment || null,
      is_discount: category === 'revenue' ? isDiscount : false,
      bank_account_id: selectedAccountId,
      reference_document: referenceDocument.trim() || null,
      paid_to: isDebitCategory ? paidTo.trim() || null : null,
      is_sim_parameter: isSimParameter,
      series_id: seriesId,
      cascade_to_series: cascadeToSeries,
      ...recurrenceFields,
    }

    // "Same day" settles each occurrence on its own entry_date (no gap —
    // settlement_date === entry_date is exactly what gl_engine treats as
    // "no separate settlement leg", i.e. paid the moment it's incurred).
    // "Select date" preserves whatever gap the first occurrence's own
    // settlement date has from its entry_date, and re-applies that same gap
    // to every later occurrence instead of pinning them all to one date.
    // Monthly/Biweekly instead resolve to whichever configured payday(s)
    // land on or after each occurrence's own date, same as a real bill's
    // due date would.
    const settlementOffsetDays =
      settlementScheduleMode === 'custom' && settlementDate ? daysBetweenIso(entryDate, settlementDate) : 0

    const buildSettlementDate = (occurrenceEntryDate) => {
      if (!selectedTreatment?.settlementLabel) return null
      if (!repeat) return settlementDate || null
      if (frequency === 'monthly') return resolveNextPayday(calendarMode, occurrenceEntryDate, [Number(paymentDay1)])
      if (frequency === 'biweekly') {
        return resolveNextPayday(calendarMode, occurrenceEntryDate, [Number(paymentDay1), Number(paymentDay2)])
      }
      if (settlementScheduleMode === 'sameDay') return occurrenceEntryDate
      return settlementDate ? shiftIsoDate(occurrenceEntryDate, settlementOffsetDays) : null
    }

    setSaving(true)
    setError('')
    try {
      await onSave(
        dates.map((occurrenceEntryDate) => ({
          ...basePayload,
          entry_date: occurrenceEntryDate,
          settlement_date: buildSettlementDate(occurrenceEntryDate),
        })),
      )
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
    ? buildRecurrenceDates(calendarMode, entryDate, {
        frequency,
        customUnit,
        interval: repeatInterval,
        untilIsoDate: untilDate,
        biweeklyDays: [Number(recurrenceDay1), Number(recurrenceDay2)],
      }).length
    : 0

  // Shown regardless of whether "Repeat this entry" is checked, so editing
  // an entry immediately reveals the pattern it was saved with — checking
  // the box only becomes necessary to actually change it or add more.
  const savedRecurrenceLabel = (() => {
    if (!isEditMode || !initialEntry?.recurrence_frequency) return null
    const savedFrequencyMeta = FREQUENCIES.find((item) => item.key === initialEntry.recurrence_frequency)
    if (initialEntry.recurrence_frequency === 'biweekly') {
      const parts = [`Biweekly (days ${initialEntry.recurrence_interval} & ${initialEntry.recurrence_custom_unit})`]
      if (initialEntry.recurrence_until_date) parts.push(`until ${initialEntry.recurrence_until_date}`)
      return parts.join(', ')
    }
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
            <>
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
              <label>
                Short description
                <input
                  type="text"
                  value={entryType}
                  onChange={(event) => setEntryType(event.target.value)}
                  placeholder="e.g. March router replacement"
                />
              </label>
            </>
          )}

          {category === 'cos' && (
            <label>
              Description
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

          {selectedTreatment?.settlementLabel && !repeat && (
            <label>
              {selectedTreatment.settlementLabel}
              {renderDateInput(settlementDate, setSettlementDate, selectedTreatment.settlementLabel)}
            </label>
          )}

          {selectedTreatment?.settlementLabel && repeat && (
            <div className="commercial-ops-modal__settlement-schedule">
              <span className="commercial-ops-modal__treatments-label">{selectedTreatment.settlementLabel} (each occurrence)</span>
              {frequency === 'monthly' ? (
                <label>
                  Pay on day
                  <select value={paymentDay1} onChange={(event) => setPaymentDay1(Number(event.target.value))}>
                    {DAYS_1_TO_30.map((day) => (
                      <option key={day} value={day}>
                        {day}
                      </option>
                    ))}
                  </select>
                  of each month
                </label>
              ) : frequency === 'biweekly' ? (
                <div className="commercial-ops-modal__repeat-row commercial-ops-modal__repeat-row--paydays">
                  <label>
                    Pay on day
                    <select value={paymentDay1} onChange={(event) => setPaymentDay1(Number(event.target.value))}>
                      {DAYS_1_TO_30.map((day) => (
                        <option key={day} value={day}>
                          {day}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    and day
                    <select value={paymentDay2} onChange={(event) => setPaymentDay2(Number(event.target.value))}>
                      {DAYS_1_TO_30.map((day) => (
                        <option key={day} value={day}>
                          {day}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className="commercial-ops-modal__repeat-unit">of each month</span>
                </div>
              ) : (
                <>
                  <label className="commercial-ops-modal__radio">
                    <input
                      type="radio"
                      name="settlement-schedule-mode"
                      value="sameDay"
                      checked={settlementScheduleMode === 'sameDay'}
                      onChange={() => setSettlementScheduleMode('sameDay')}
                    />
                    Same day as each entry (default)
                  </label>
                  <label className="commercial-ops-modal__radio">
                    <input
                      type="radio"
                      name="settlement-schedule-mode"
                      value="custom"
                      checked={settlementScheduleMode === 'custom'}
                      onChange={() => setSettlementScheduleMode('custom')}
                    />
                    Select date
                  </label>
                  {settlementScheduleMode === 'custom' && (
                    <>
                      {renderDateInput(settlementDate, setSettlementDate, selectedTreatment.settlementLabel)}
                      <p className="commercial-ops-modal__repeat-hint">
                        The gap between this date and the entry date above carries forward to every later occurrence.
                      </p>
                    </>
                  )}
                </>
              )}
            </div>
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

          {isEditMode && initialEntry?.series_id && seriesEntryCount > 1 && (
            <label className="commercial-ops-modal__checkbox" title="Every field except each entry's own date(s) will be copied to the rest of the series.">
              <input type="checkbox" checked={cascadeToSeries} onChange={(event) => setCascadeToSeries(event.target.checked)} />
              Apply these changes to all {seriesEntryCount} entries in this series
            </label>
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
                      <span className="commercial-ops-modal__repeat-unit">{unitLabel}</span>
                    )}
                  </>
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
