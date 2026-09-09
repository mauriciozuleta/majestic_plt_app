import { useEffect, useMemo, useState } from 'react'
import {
  createCommercialOperationEntry,
  deleteCommercialOperationEntry,
  fetchCommercialOperationEntries,
} from '../../../../../services/commercialOperations'
import { fetchSettings } from '../../../../../services/settings'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import { createSimParameter } from '../../../../../services/simParameters'
import JumpToDatePicker from './JumpToDatePicker'
import MonthView from './MonthView'
import DayView from './DayView'
import YearView from './YearView'
import AddEntryModal from './AddEntryModal'
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

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const [settings, nextEntries] = await Promise.all([fetchSettings(), fetchCommercialOperationEntries(companyId)])
      const mode = settings.calendar_mode ?? 'real'
      setCalendarMode(mode)
      setEntries(nextEntries)
      setReferenceDate((prev) => prev ?? getDefaultCalendarDate(mode))
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
    const entries = Array.isArray(payloads) ? payloads : [payloads]
    for (const { is_sim_parameter, ...entry } of entries) {
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

  const handleDeleteEntry = async (entryId) => {
    await deleteCommercialOperationEntry(companyId, entryId)
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
            {category.label} total: ${category.total.toLocaleString()}
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
      </div>

      {error && <div className="commercial-ops__error">{error}</div>}

      {viewMode === 'month' && (
        <MonthView calendarMode={calendarMode} referenceDate={referenceDate} entriesByDate={entriesByDate} onSelectDay={handleSelectDay} />
      )}
      {viewMode === 'day' && <DayView dayEntries={dayEntries} onDeleteEntry={handleDeleteEntry} />}
      {viewMode === 'year' && (
        <YearView calendarMode={calendarMode} referenceDate={referenceDate} entries={entries} onSelectMonth={handleSelectMonth} />
      )}

      {modalCategory && (
        <AddEntryModal
          category={modalCategory}
          initialDate={referenceDate}
          calendarMode={calendarMode}
          onSave={handleSaveEntry}
          onCancel={() => setModalCategory(null)}
        />
      )}
    </div>
  )
}

export default CommercialOperationsView
