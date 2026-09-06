import { useEffect, useMemo, useState } from 'react'
import {
  createCommercialOperationEntry,
  deleteCommercialOperationEntry,
  fetchCommercialOperationEntries,
} from '../../../../../services/commercialOperations'
import { fetchSettings } from '../../../../../services/settings'
import { getDefaultCalendarDate } from '../../../../../services/calendarDates'
import MonthView from './MonthView'
import DayView from './DayView'
import AddEntryModal from './AddEntryModal'
import { getDayLabel, getMonthLabel, shiftIsoDate, shiftMonth } from './calendarViewMath'
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

  const handleAddNew = (categoryKey) => setModalCategory(categoryKey)

  const handleSaveEntry = async (payload) => {
    await createCommercialOperationEntry(companyId, payload)
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

  const handlePrev = () => {
    setReferenceDate((prev) => (viewMode === 'month' ? shiftMonth(calendarMode, prev, -1) : shiftIsoDate(prev, -1)))
  }

  const handleNext = () => {
    setReferenceDate((prev) => (viewMode === 'month' ? shiftMonth(calendarMode, prev, 1) : shiftIsoDate(prev, 1)))
  }

  const handleToday = () => setReferenceDate(getDefaultCalendarDate(calendarMode))

  if (loading || !referenceDate) {
    return <div className="commercial-ops-status">Loading commercial operations...</div>
  }

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
        </div>

        <div className="commercial-ops__nav">
          <button type="button" className="commercial-ops__nav-btn" onClick={handlePrev} aria-label="Previous">
            {'<'}
          </button>
          <strong className="commercial-ops__period-label">
            {viewMode === 'month' ? getMonthLabel(calendarMode, referenceDate) : getDayLabel(calendarMode, referenceDate)}
          </strong>
          <button type="button" className="commercial-ops__nav-btn" onClick={handleNext} aria-label="Next">
            {'>'}
          </button>
          <button type="button" className="commercial-ops__today-btn" onClick={handleToday}>
            Today
          </button>
        </div>
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

      {viewMode === 'month' ? (
        <MonthView calendarMode={calendarMode} referenceDate={referenceDate} entriesByDate={entriesByDate} onSelectDay={handleSelectDay} />
      ) : (
        <DayView dayEntries={dayEntries} onDeleteEntry={handleDeleteEntry} />
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
