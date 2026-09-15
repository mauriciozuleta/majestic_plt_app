import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import ExportPdfButton from '../../../../shared/PdfExport/ExportPdfButton'
import { downloadCsv } from '../../../../../utils/exportCsv'
import { fetchChartOfAccounts, fetchJournalEntries } from '../../../../../services/generalLedger'
import {
  deleteCommercialOperationEntry,
  createCommercialOperationEntry,
  fetchCommercialOperationEntries,
  updateCommercialOperationEntry,
} from '../../../../../services/commercialOperations'
import { fetchSettings } from '../../../../../services/settings'
import { createSimParameter, deleteSimParameter, fetchSimParameters } from '../../../../../services/simParameters'
import AddEntryModal from '../../OperationsTab/CommercialOperationsView/AddEntryModal'
import DateFilter from '../../../../shared/DateFilter/DateFilter'
import { buildGeneralLedgerSummary, generalLedgerToCsvRows, reportToPdfSpec } from './accountingReports'
import './Accounting.css'

const TYPE_LABELS = {
  asset: 'Assets',
  liability: 'Liabilities',
  equity: 'Equity',
  revenue: 'Revenue',
  contra_revenue: 'Contra-Revenue',
  expense: 'Expenses',
}
const TYPE_ORDER = ['asset', 'liability', 'equity', 'revenue', 'contra_revenue', 'expense']

// Payroll Schedule (Settings > Payroll Schedule > Automatic schedule) and
// the Payroll tax/benefits panels are the only things that should ever
// touch these accounts — editing or deleting a posting here directly would
// just get silently reverted (or duplicated) the next time payroll data
// changes and the schedule re-syncs. Any journal entry touching one of
// these codes is locked from this view; edit the underlying payroll data
// instead.
const PAYROLL_ACCOUNT_CODES = new Set(['6100', '6200', '6300', '2200', '2250', '2300'])

function money(value) {
  const amount = Number(value) || 0
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function sortRowsForDisplay(rows, sortMode) {
  if (sortMode === 'date') return rows
  const sorted = [...rows]
  if (sortMode === 'name') {
    sorted.sort((a, b) => (a.memo || '').localeCompare(b.memo || ''))
  } else if (sortMode === 'amount-asc' || sortMode === 'amount-desc') {
    const rowAmount = (row) => row.debit || row.credit || 0
    sorted.sort((a, b) => (sortMode === 'amount-asc' ? rowAmount(a) - rowAmount(b) : rowAmount(b) - rowAmount(a)))
  }
  return sorted
}

function GeneralLedgerView() {
  const { companyId } = useParams()
  const [accounts, setAccounts] = useState([])
  const [journalEntries, setJournalEntries] = useState([])
  const [commercialOperationEntries, setCommercialOperationEntries] = useState([])
  const [calendarMode, setCalendarMode] = useState('real')
  const [simParameterEntryIds, setSimParameterEntryIds] = useState(() => new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingEntry, setEditingEntry] = useState(null)
  const [actionError, setActionError] = useState('')
  // Every account starts expanded; collapsing one just hides its posting
  // table (the balance stays visible in the header either way).
  const [collapsedAccountIds, setCollapsedAccountIds] = useState(() => new Set())
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedSourceIds, setSelectedSourceIds] = useState(() => new Set())
  const [dateFilterPrefix, setDateFilterPrefix] = useState('')
  // Per-account display order — sorting only ever reorders what's shown;
  // the running Balance column is computed once in true chronological
  // order below, before this sort is applied, so re-sorting by name or
  // amount never makes the balance figures themselves wrong.
  const [sortModeByAccount, setSortModeByAccount] = useState(() => new Map())

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [nextAccounts, nextJournalEntries, nextOpsEntries, settings, simParameters] = await Promise.all([
        fetchChartOfAccounts(companyId),
        fetchJournalEntries(companyId),
        fetchCommercialOperationEntries(companyId),
        fetchSettings(),
        fetchSimParameters(companyId),
      ])
      setAccounts(nextAccounts)
      setJournalEntries(nextJournalEntries)
      setCommercialOperationEntries(nextOpsEntries)
      setCalendarMode(settings.calendar_mode ?? 'real')
      setSimParameterEntryIds(new Set(simParameters.map((item) => item.entry_id)))
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

  // Every date in this app — real or simulation — is a plain ISO
  // YYYY-MM-DD string, so the filter (built by DateFilter into the right
  // length prefix for Day/Month/Year) is just a startsWith check.
  const filteredJournalEntries = useMemo(() => {
    if (!dateFilterPrefix) return journalEntries
    return journalEntries.filter((entry) => entry.entry_date.startsWith(dateFilterPrefix))
  }, [journalEntries, dateFilterPrefix])

  // Whether ANY line of this journal entry touches a payroll-related
  // account — both legs of a payroll posting (e.g. 6100/2200, or a later
  // settlement's 2200/1000) need to be locked together, not just whichever
  // account's table you happen to be looking at.
  const payrollJournalEntryIds = useMemo(() => {
    const ids = new Set()
    filteredJournalEntries.forEach((entry) => {
      if (entry.lines.some((line) => PAYROLL_ACCOUNT_CODES.has(line.account_code))) ids.add(entry.id)
    })
    return ids
  }, [filteredJournalEntries])

  const ledgerByAccount = useMemo(() => {
    const postings = new Map()
    filteredJournalEntries.forEach((entry) => {
      entry.lines.forEach((line) => {
        const list = postings.get(line.account_id) || []
        list.push({
          date: entry.entry_date,
          memo: entry.memo,
          debit: line.debit,
          credit: line.credit,
          sourceType: entry.source_type,
          sourceId: entry.source_id,
          isLocked: payrollJournalEntryIds.has(entry.id),
        })
        postings.set(line.account_id, list)
      })
    })
    postings.forEach((list) => list.sort((a, b) => a.date.localeCompare(b.date)))
    return postings
  }, [filteredJournalEntries, payrollJournalEntryIds])

  const groupedAccounts = useMemo(() => {
    const groups = new Map(TYPE_ORDER.map((type) => [type, []]))
    accounts
      .filter((account) => (ledgerByAccount.get(account.id) || []).length > 0)
      .forEach((account) => {
        const list = groups.get(account.account_type) || []
        list.push(account)
        groups.set(account.account_type, list)
      })
    return TYPE_ORDER.map((type) => ({ type, accounts: groups.get(type) || [] })).filter((group) => group.accounts.length > 0)
  }, [accounts, ledgerByAccount])

  // Which entries the checkboxes are actually allowed to select — every
  // posting on screen that isn't payroll-locked, deduped by the
  // CommercialOperationEntry id underneath it (the same entry can post to
  // more than one account, e.g. Cash and Revenue, and should count once).
  const selectableSourceIds = useMemo(() => {
    const ids = new Set()
    ledgerByAccount.forEach((postings) => {
      postings.forEach((posting) => {
        if (!posting.isLocked && posting.sourceType === 'commercial_operation_entry') ids.add(posting.sourceId)
      })
    })
    return ids
  }, [ledgerByAccount])

  if (loading) return <div className="accounting-view__status">Loading general ledger...</div>
  if (error) return <div className="accounting-view__status accounting-view__status--error">{error}</div>

  const handleExportCsv = () => {
    const { headers, rows } = generalLedgerToCsvRows(accounts, filteredJournalEntries)
    downloadCsv('general-ledger.csv', headers, rows)
  }

  const toggleAccountCollapsed = (accountId) => {
    setCollapsedAccountIds((prev) => {
      const next = new Set(prev)
      if (next.has(accountId)) next.delete(accountId)
      else next.add(accountId)
      return next
    })
  }

  const toggleSelectionMode = () => {
    setSelectionMode((prev) => !prev)
    setSelectedSourceIds(new Set())
    setActionError('')
  }

  const toggleSelected = (sourceId) => {
    setSelectedSourceIds((prev) => {
      const next = new Set(prev)
      if (next.has(sourceId)) next.delete(sourceId)
      else next.add(sourceId)
      return next
    })
  }

  // Selects (or, if every one is already selected, deselects) every
  // selectable entry shown in one account's table — deduped, since the same
  // entry can post twice to the same account (e.g. a prepaid expense's
  // initial debit and later settlement credit both touch that account).
  const toggleSelectAllForAccount = (selectableIds) => {
    const uniqueIds = [...new Set(selectableIds)]
    if (uniqueIds.length === 0) return
    const allSelected = uniqueIds.every((id) => selectedSourceIds.has(id))
    setSelectedSourceIds((prev) => {
      const next = new Set(prev)
      uniqueIds.forEach((id) => (allSelected ? next.delete(id) : next.add(id)))
      return next
    })
  }

  const setSortModeForAccount = (accountId, mode) => {
    setSortModeByAccount((prev) => new Map(prev).set(accountId, mode))
  }

  const handleEditSelected = () => {
    const [sourceId] = selectedSourceIds
    const entry = commercialOperationEntries.find((item) => item.id === sourceId)
    if (!entry) {
      setActionError('Could not find that entry — it may have already been changed elsewhere. Reloading…')
      reload()
      return
    }
    setActionError('')
    setEditingEntry(entry)
  }

  const handleDeleteSelected = async () => {
    const count = selectedSourceIds.size
    if (count === 0) return
    if (!window.confirm(`Delete ${count} ${count === 1 ? 'entry' : 'entries'}? This removes ${count === 1 ? 'it' : 'them'} from Commercial Operations too, and un-posts ${count === 1 ? 'it' : 'them'} from the ledger.`)) {
      return
    }
    setActionError('')
    try {
      for (const sourceId of selectedSourceIds) {
        // eslint-disable-next-line no-await-in-loop
        await deleteCommercialOperationEntry(companyId, sourceId)
      }
      setSelectedSourceIds(new Set())
      setSelectionMode(false)
      await reload()
    } catch (err) {
      setActionError(err.message || 'Failed to delete the selected entries.')
    }
  }

  // Same edit-then-repeat semantics as Commercial Operations' own edit flow:
  // the first payload updates the entry being edited, any further payloads
  // (from "Repeat this entry" used while editing) are created as brand-new
  // entries going forward. Separately, "Apply to all entries in this
  // series" cascades every field except each sibling's own date(s) to every
  // other entry sharing the same series_id.
  const handleUpdateEntry = async (payloads) => {
    setActionError('')
    try {
      const [firstPayload, ...restPayloads] = Array.isArray(payloads) ? payloads : [payloads]
      const { is_sim_parameter: firstIsSimParameter, cascade_to_series: cascadeToSeries, ...firstEntry } = firstPayload
      await updateCommercialOperationEntry(companyId, editingEntry.id, firstEntry)
      if (firstIsSimParameter) {
        await createSimParameter(companyId, editingEntry.id)
      } else {
        await deleteSimParameter(companyId, editingEntry.id).catch(() => undefined)
      }
      if (cascadeToSeries && firstEntry.series_id) {
        const siblings = commercialOperationEntries.filter(
          (entry) => entry.series_id === firstEntry.series_id && entry.id !== editingEntry.id,
        )
        for (const sibling of siblings) {
          // eslint-disable-next-line no-await-in-loop
          await updateCommercialOperationEntry(companyId, sibling.id, {
            ...firstEntry,
            entry_date: sibling.entry_date,
            settlement_date: sibling.settlement_date,
          })
        }
      }
      for (const { is_sim_parameter, cascade_to_series: _cascadeToSeries, ...entry } of restPayloads) {
        // eslint-disable-next-line no-await-in-loop
        const created = await createCommercialOperationEntry(companyId, entry)
        if (is_sim_parameter) {
          // eslint-disable-next-line no-await-in-loop
          await createSimParameter(companyId, created.id)
        }
      }
      setEditingEntry(null)
      setSelectedSourceIds(new Set())
      setSelectionMode(false)
      await reload()
    } catch (err) {
      setActionError(err.message || 'Failed to save the entry.')
    }
  }

  if (journalEntries.length === 0) {
    return (
      <div className="accounting-view__status">
        No ledger activity yet. Postings appear here automatically once a Commercial Operations entry is saved with an
        Accounting Treatment selected.
      </div>
    )
  }

  return (
    <div className="accounting-view general-ledger">
      <div className="accounting-view__toolbar">
        <div className="accounting-view__export-actions">
          <button type="button" className="accounting-view__csv-btn" onClick={handleExportCsv}>
            Export CSV
          </button>
          <ExportPdfButton
            spec={reportToPdfSpec(buildGeneralLedgerSummary(accounts, filteredJournalEntries), 'All time')}
            label="Export PDF"
          />
        </div>
        <DateFilter calendarMode={calendarMode} onChange={setDateFilterPrefix} />
        <div className="general-ledger__selection-toolbar">
          {selectionMode ? (
            <>
              <span className="general-ledger__selection-count">
                {selectedSourceIds.size} selected
                {selectableSourceIds.size > 0 ? ` of ${selectableSourceIds.size} editable` : ''}
              </span>
              <button type="button" className="accounting-view__csv-btn" disabled={selectedSourceIds.size !== 1} onClick={handleEditSelected}>
                Edit
              </button>
              <button
                type="button"
                className="accounting-view__csv-btn general-ledger__delete-btn"
                disabled={selectedSourceIds.size === 0}
                onClick={handleDeleteSelected}
              >
                Delete{selectedSourceIds.size > 0 ? ` (${selectedSourceIds.size})` : ''}
              </button>
              <button type="button" className="accounting-view__csv-btn" onClick={toggleSelectionMode}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className="accounting-view__csv-btn" onClick={toggleSelectionMode}>
              Select entries
            </button>
          )}
        </div>
      </div>
      {actionError && <div className="accounting-view__status accounting-view__status--error">{actionError}</div>}
      {groupedAccounts.length === 0 && (
        <div className="accounting-view__status">No postings match this date filter.</div>
      )}
      {groupedAccounts.map((group) => (
        <div key={group.type} className="general-ledger__group">
          <h4 className="general-ledger__group-title">{TYPE_LABELS[group.type] ?? group.type}</h4>
          {group.accounts.map((account) => {
            const postings = ledgerByAccount.get(account.id) || []
            const rowsWithBalance = []
            for (const posting of postings) {
              const previousBalance = rowsWithBalance.length ? rowsWithBalance[rowsWithBalance.length - 1].balance : 0
              const delta =
                account.normal_balance === 'debit' ? posting.debit - posting.credit : posting.credit - posting.debit
              rowsWithBalance.push({ ...posting, balance: previousBalance + delta })
            }
            const endingBalance = rowsWithBalance.length ? rowsWithBalance[rowsWithBalance.length - 1].balance : 0
            const isCollapsed = collapsedAccountIds.has(account.id)
            const sortMode = sortModeByAccount.get(account.id) || 'date'
            const displayRows = sortRowsForDisplay(rowsWithBalance, sortMode)
            const selectableIdsForAccount = rowsWithBalance
              .filter((posting) => !posting.isLocked && posting.sourceType === 'commercial_operation_entry')
              .map((posting) => posting.sourceId)
            const uniqueSelectableIds = [...new Set(selectableIdsForAccount)]
            const isAllSelectedForAccount =
              uniqueSelectableIds.length > 0 && uniqueSelectableIds.every((id) => selectedSourceIds.has(id))

            return (
              <div key={account.id} className="general-ledger__account">
                <div className="general-ledger__account-header">
                  <button
                    type="button"
                    className="general-ledger__account-title"
                    onClick={() => toggleAccountCollapsed(account.id)}
                    aria-expanded={!isCollapsed}
                  >
                    <span className={`general-ledger__account-chevron ${isCollapsed ? '' : 'is-expanded'}`}>▸</span>
                    <span className="general-ledger__account-code">{account.code}</span>
                    {account.name}
                  </button>
                  <div className="general-ledger__account-header-actions">
                    {!isCollapsed && (
                      <label className="general-ledger__sort-select">
                        Filter by:
                        <select value={sortMode} onChange={(event) => setSortModeForAccount(account.id, event.target.value)}>
                          <option value="date">Date</option>
                          <option value="name">Name</option>
                          <option value="amount-asc">Amount (low to high)</option>
                          <option value="amount-desc">Amount (high to low)</option>
                        </select>
                      </label>
                    )}
                    <span className="general-ledger__account-balance">{money(endingBalance)}</span>
                  </div>
                </div>
                {!isCollapsed && (
                  <>
                    <div className="general-ledger__table-scroll">
                      <table className="accounting-view__table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Memo</th>
                            <th className="num">Debit</th>
                            <th className="num">Credit</th>
                            <th className="num">Balance</th>
                            {selectionMode && (
                              <th className="general-ledger__row-select">
                                <input
                                  type="checkbox"
                                  checked={isAllSelectedForAccount}
                                  disabled={uniqueSelectableIds.length === 0}
                                  onChange={() => toggleSelectAllForAccount(uniqueSelectableIds)}
                                  title="Select all"
                                />
                              </th>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {displayRows.map((posting, index) => {
                            const isSelectable = !posting.isLocked && posting.sourceType === 'commercial_operation_entry'
                            return (
                              <tr key={index}>
                                <td>{posting.date}</td>
                                <td>{posting.memo}</td>
                                <td className="num">{posting.debit ? money(posting.debit) : ''}</td>
                                <td className="num">{posting.credit ? money(posting.credit) : ''}</td>
                                <td className="num">{money(posting.balance)}</td>
                                {selectionMode && (
                                  <td className="general-ledger__row-select">
                                    {isSelectable ? (
                                      <input
                                        type="checkbox"
                                        checked={selectedSourceIds.has(posting.sourceId)}
                                        onChange={() => toggleSelected(posting.sourceId)}
                                      />
                                    ) : (
                                      <span
                                        className="general-ledger__locked"
                                        title="Managed by Payroll — edit the payroll data instead."
                                      >
                                        {posting.isLocked ? 'Payroll' : '—'}
                                      </span>
                                    )}
                                  </td>
                                )}
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
          })}
        </div>
      ))}

      {editingEntry && (
        <AddEntryModal
          companyId={companyId}
          category={editingEntry.category}
          calendarMode={calendarMode}
          initialEntry={editingEntry}
          initialIsSimParameter={simParameterEntryIds.has(editingEntry.id)}
          seriesEntryCount={
            editingEntry.series_id
              ? commercialOperationEntries.filter((entry) => entry.series_id === editingEntry.series_id).length
              : 0
          }
          onSave={handleUpdateEntry}
          onCancel={() => setEditingEntry(null)}
        />
      )}
    </div>
  )
}

export default GeneralLedgerView
