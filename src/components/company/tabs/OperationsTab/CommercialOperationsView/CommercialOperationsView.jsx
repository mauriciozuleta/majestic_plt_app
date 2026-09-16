import { useEffect, useMemo, useState } from 'react'
import {
  createCommercialOperationEntry,
  deleteCommercialOperationEntry,
  fetchCommercialOperationEntries,
  updateCommercialOperationEntry,
} from '../../../../../services/commercialOperations'
import { fetchSettings } from '../../../../../services/settings'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import { createSimParameter, deleteSimParameter, fetchSimParameters } from '../../../../../services/simParameters'
import { createBankTransfer, fetchBankAccounts } from '../../../../../services/bankAccounts'
import JumpToDatePicker from './JumpToDatePicker'
import MonthView from './MonthView'
import DayView from './DayView'
import YearView from './YearView'
import AddEntryModal from './AddEntryModal'
import TransferFundsModal from '../../FinancialTab/TransferFundsModal'
import {
  getDayLabel,
  getMonthLabel,
  getMonthRange,
  getYear,
  getYearLabel,
  getYearRange,
  setYear,
  shiftIsoDate,
  shiftMonth,
} from './calendarViewMath'
import { entriesInRange, sumByCategory } from './entryTotals'
import { CATEGORIES } from './categories'
import './CommercialOperationsView.css'

function CommercialOperationsView({ companyId }) {
  const [calendarMode, setCalendarMode] = useState('real')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [viewMode, setViewMode] = useState('month')
  const [referenceDate, setReferenceDate] = useState(null)
  const [modalCategory, setModalCategory] = useState(null)
  const [editingEntry, setEditingEntry] = useState(null)
  const [simParameterEntryIds, setSimParameterEntryIds] = useState(() => new Set())
  const [bankAccounts, setBankAccounts] = useState([])
  const [transferModalOpen, setTransferModalOpen] = useState(false)

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [settings, nextEntries, simParameters, accounts] = await Promise.all([
        fetchSettings(),
        fetchCommercialOperationEntries(companyId),
        fetchSimParameters(companyId),
        fetchBankAccounts(companyId),
      ])
      const mode = settings.calendar_mode ?? 'real'
      setCalendarMode(mode)
      setEntries(nextEntries)
      setSimParameterEntryIds(new Set(simParameters.map((item) => item.entry_id)))
      setBankAccounts(accounts)
      setReferenceDate((prev) => prev ?? getDefaultCalendarDate(mode))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Moving money between your own accounts (e.g. into a reserve) isn't an
  // expense or COS — it's a pure internal transfer, with no P&L effect. This
  // opens the same Inter-bank Transfer form Bank Accounts uses, replacing
  // whichever Add-entry modal called it (both are exclusive of each other).
  const handleOpenTransfer = () => {
    setModalCategory(null)
    setEditingEntry(null)
    setTransferModalOpen(true)
  }

  const handleTransfer = async (payloads) => {
    for (const payload of payloads) {
      // eslint-disable-next-line no-await-in-loop
      await createBankTransfer(payload)
    }
    setTransferModalOpen(false)
    await reload()
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId])

  const entriesByDate = useMemo(() => {
    const map = new Map()
    entries.forEach((entry) => {
      const list = map.get(entry.entry_date) || []
      list.push(entry)
      map.set(entry.entry_date, list)
    })
    return map
  }, [entries])

  const dayEntries = referenceDate ? entriesByDate.get(referenceDate) || [] : []

  const periodTotals = useMemo(() => {
    if (!referenceDate) return []
    if (viewMode === 'day') return sumByCategory(entriesByDate.get(referenceDate) || [])
    if (viewMode === 'month') {
      const { start, endExclusive } = getMonthRange(calendarMode, referenceDate)
      return sumByCategory(entriesInRange(entries, start, endExclusive))
    }
    const { start, endExclusive } = getYearRange(calendarMode, referenceDate)
    return sumByCategory(entriesInRange(entries, start, endExclusive))
  }, [viewMode, referenceDate, calendarMode, entries, entriesByDate])

  const handleAddNew = (categoryKey) => setModalCategory(categoryKey)

  const handleSaveEntry = async (payloads) => {
    const newEntries = Array.isArray(payloads) ? payloads : [payloads]
    for (const { is_sim_parameter, cascade_to_series: _cascadeToSeries, ...entry } of newEntries) {
      // eslint-disable-next-line no-await-in-loop
      const created = await createCommercialOperationEntry(companyId, entry)
      if (is_sim_parameter) {
        // eslint-disable-next-line no-await-in-loop
        await createSimParameter(companyId, created.id)
      }
    }
    setModalCategory(null)
    await reload()
  }

  // How many entries share each series_id — DayView needs this to know
  // whether a given entry actually has siblings worth offering a
  // "delete the whole series" choice for (a series_id shared by only one
  // row, e.g. after its siblings were already deleted, is no series at all).
  const seriesCounts = useMemo(() => {
    const counts = new Map()
    entries.forEach((entry) => {
      if (!entry.series_id) return
      counts.set(entry.series_id, (counts.get(entry.series_id) || 0) + 1)
    })
    return counts
  }, [entries])

  const handleDeleteEntry = async (entryId, { deleteSeries = false } = {}) => {
    if (deleteSeries) {
      const entry = entries.find((item) => item.id === entryId)
      const siblingIds = entry?.series_id ? entries.filter((item) => item.series_id === entry.series_id).map((item) => item.id) : [entryId]
      for (const siblingId of siblingIds) {
        // eslint-disable-next-line no-await-in-loop
        await deleteCommercialOperationEntry(companyId, siblingId)
      }
    } else {
      await deleteCommercialOperationEntry(companyId, entryId)
    }
    await reload()
  }

  const handleEditEntry = (entry) => setEditingEntry(entry)

  const seriesEntryCount = editingEntry?.series_id
    ? entries.filter((entry) => entry.series_id === editingEntry.series_id).length
    : 0

  const handleUpdateEntry = async (payloads) => {
    // Editing normally touches just the one entry, but the form's "Repeat
    // this entry" can still be used while editing — the first date updates
    // the entry being edited, and any further dates are created as brand
    // new entries going forward. Separately, "Apply to all entries in this
    // series" cascades every field except each sibling's own date(s) to
    // every other entry sharing the same series_id.
    const [firstPayload, ...restPayloads] = Array.isArray(payloads) ? payloads : [payloads]
    const { is_sim_parameter: firstIsSimParameter, cascade_to_series: cascadeToSeries, ...firstEntry } = firstPayload
    await updateCommercialOperationEntry(companyId, editingEntry.id, firstEntry)
    if (firstIsSimParameter) {
      await createSimParameter(companyId, editingEntry.id)
    } else {
      await deleteSimParameter(companyId, editingEntry.id).catch(() => undefined)
    }
    if (cascadeToSeries && firstEntry.series_id) {
      const siblings = entries.filter((entry) => entry.series_id === firstEntry.series_id && entry.id !== editingEntry.id)
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
    await reload()
  }

  const handleSelectDay = (isoDate) => {
    setReferenceDate(isoDate)
    setViewMode('day')
  }

  const handleSelectMonth = (isoDate) => {
    setReferenceDate(isoDate)
    setViewMode('month')
  }

  const handlePrev = () => {
    setReferenceDate((prev) => {
      if (viewMode === 'year') return setYear(calendarMode, prev, getYear(calendarMode, prev) - 1)
      if (viewMode === 'month') return shiftMonth(calendarMode, prev, -1)
      return shiftIsoDate(prev, -1)
    })
  }

  const handleNext = () => {
    setReferenceDate((prev) => {
      if (viewMode === 'year') return setYear(calendarMode, prev, getYear(calendarMode, prev) + 1)
      if (viewMode === 'month') return shiftMonth(calendarMode, prev, 1)
      return shiftIsoDate(prev, 1)
    })
  }

  const handleJumpToDate = (isoDate) => setReferenceDate(isoDate)

  const handleYearChange = (year) => {
    setReferenceDate((prev) => setYear(calendarMode, prev, year))
  }

  const yearOptions = useMemo(() => {
    if (calendarMode === 'simulation') {
      return Array.from({ length: 21 }, (_, index) => index + 1)
    }
    const currentYear = new Date().getFullYear()
    return Array.from({ length: 21 }, (_, index) => currentYear - 10 + index)
  }, [calendarMode])

  if (loading || !referenceDate) {
    return <div className="commercial-ops-status">Loading commercial operations...</div>
  }

  const periodLabel =
    viewMode === 'month'
      ? getMonthLabel(calendarMode, referenceDate)
      : viewMode === 'year'
        ? getYearLabel(calendarMode, referenceDate)
        : getDayLabel(calendarMode, referenceDate)

  return (
    <div className="commercial-ops">
      <div className="commercial-ops__toolbar">
        <div className="commercial-ops__view-toggle">
          <button type="button" className={viewMode === 'day' ? 'is-active' : ''} onClick={() => setViewMode('day')}>
            Day
          </button>
          <button type="button" className={viewMode === 'month' ? 'is-active' : ''} onClick={() => setViewMode('month')}>
            Month
          </button>
          <button type="button" className={viewMode === 'year' ? 'is-active' : ''} onClick={() => setViewMode('year')}>
            Year
          </button>
        </div>

        <div className="commercial-ops__nav">
          <button type="button" className="commercial-ops__nav-btn" onClick={handlePrev} aria-label="Previous">
            {'<'}
          </button>
          <strong className="commercial-ops__period-label">{periodLabel}</strong>
          <button type="button" className="commercial-ops__nav-btn" onClick={handleNext} aria-label="Next">
            {'>'}
          </button>
        </div>

        <label className="commercial-ops__year-selector">
          Year
          <select value={getYear(calendarMode, referenceDate)} onChange={(event) => handleYearChange(Number(event.target.value))}>
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>

        <JumpToDatePicker calendarMode={calendarMode} value={referenceDate} onChange={handleJumpToDate} />
      </div>

      <div className="commercial-ops__totals">
        {periodTotals.map((category) => (
          <span key={category.key} className="commercial-ops__total-pill" style={{ borderColor: category.color, color: category.color }}>
            {category.label} total: ${category.total.toLocaleString('en-US')}
          </span>
        ))}
      </div>

      <div className="commercial-ops__category-actions">
        {CATEGORIES.map((category) => (
          <button
            key={category.key}
            type="button"
            className="commercial-ops__add-btn"
            style={{ borderColor: category.color, color: category.color }}
            onClick={() => handleAddNew(category.key)}
          >
            + Add {category.label}
          </button>
        ))}
        <button
          type="button"
          className="commercial-ops__add-btn"
          style={{ borderColor: 'var(--accent-teal)', color: 'var(--accent-teal-text)' }}
          onClick={handleOpenTransfer}
        >
          + Add Interbank Transfer
        </button>
      </div>

      {error && <div className="commercial-ops__error">{error}</div>}

      {viewMode === 'month' && (
        <MonthView calendarMode={calendarMode} referenceDate={referenceDate} entriesByDate={entriesByDate} onSelectDay={handleSelectDay} />
      )}
      {viewMode === 'day' && (
        <DayView dayEntries={dayEntries} seriesCounts={seriesCounts} onDeleteEntry={handleDeleteEntry} onEditEntry={handleEditEntry} />
      )}
      {viewMode === 'year' && (
        <YearView calendarMode={calendarMode} referenceDate={referenceDate} entries={entries} onSelectMonth={handleSelectMonth} />
      )}

      {modalCategory && (
        <AddEntryModal
          companyId={companyId}
          category={modalCategory}
          initialDate={referenceDate}
          calendarMode={calendarMode}
          onSave={handleSaveEntry}
          onCancel={() => setModalCategory(null)}
          onOpenTransfer={handleOpenTransfer}
        />
      )}

      {editingEntry && (
        <AddEntryModal
          companyId={companyId}
          category={editingEntry.category}
          initialDate={referenceDate}
          calendarMode={calendarMode}
          initialEntry={editingEntry}
          initialIsSimParameter={simParameterEntryIds.has(editingEntry.id)}
          seriesEntryCount={seriesEntryCount}
          onSave={handleUpdateEntry}
          onCancel={() => setEditingEntry(null)}
          onOpenTransfer={handleOpenTransfer}
        />
      )}

      {transferModalOpen && (
        <TransferFundsModal accounts={bankAccounts} onSave={handleTransfer} onCancel={() => setTransferModalOpen(false)} />
      )}
    </div>
  )
}

export default CommercialOperationsView
