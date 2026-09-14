import { useEffect, useState } from 'react'
import { DAY_OPTIONS, MONTH_OPTIONS, simDateToIsoDate } from '../SimulationCalendar/simulationCalendarMath'
import './DateFilter.css'

// A single reusable "filter by Day / Month / Year" control. Every date in
// this app — real or simulation — is stored as a plain ISO YYYY-MM-DD
// string, so filtering never needs to know which mode produced the entry
// being filtered: Day matches the full 10-character string, Month matches
// the first 7 ("YYYY-MM"), Year matches the first 4 ("YYYY"). This control
// only has to turn whatever the user picked into that same prefix string —
// simulation mode does it via simDateToIsoDate (the fictitious-epoch
// equivalent of a real date), real mode's native inputs already produce it
// directly.
function DateFilter({ calendarMode, onChange, maxYear = 20 }) {
  const [enabled, setEnabled] = useState(false)
  const [granularity, setGranularity] = useState('month')
  const [realValue, setRealValue] = useState('')
  const [simYear, setSimYear] = useState(1)
  const [simMonth, setSimMonth] = useState(1)
  const [simDay, setSimDay] = useState(1)

  useEffect(() => {
    if (!enabled) {
      onChange('')
      return
    }
    if (calendarMode === 'simulation') {
      const iso = simDateToIsoDate({ year: simYear, month: simMonth, day: simDay })
      if (granularity === 'day') onChange(iso)
      else if (granularity === 'month') onChange(iso.slice(0, 7))
      else onChange(iso.slice(0, 4))
      return
    }
    onChange(realValue)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, calendarMode, granularity, realValue, simYear, simMonth, simDay])

  const handleGranularityChange = (nextGranularity) => {
    setGranularity(nextGranularity)
    setRealValue('')
  }

  return (
    <div className="date-filter">
      <label className="date-filter__toggle">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        Filter by date
      </label>
      {enabled && (
        <>
          <select
            className="date-filter__granularity"
            value={granularity}
            onChange={(event) => handleGranularityChange(event.target.value)}
            aria-label="Filter granularity"
          >
            <option value="day">Day</option>
            <option value="month">Month</option>
            <option value="year">Year</option>
          </select>

          {calendarMode === 'simulation' ? (
            <div className="date-filter__sim-inputs">
              <select value={simYear} onChange={(event) => setSimYear(Number(event.target.value))} aria-label="Year">
                {Array.from({ length: maxYear }, (_, index) => index + 1).map((year) => (
                  <option key={year} value={year}>
                    Year {year}
                  </option>
                ))}
              </select>
              {granularity !== 'year' && (
                <select value={simMonth} onChange={(event) => setSimMonth(Number(event.target.value))} aria-label="Month">
                  {MONTH_OPTIONS.map((month) => (
                    <option key={month} value={month}>
                      Month {month}
                    </option>
                  ))}
                </select>
              )}
              {granularity === 'day' && (
                <select value={simDay} onChange={(event) => setSimDay(Number(event.target.value))} aria-label="Day">
                  {DAY_OPTIONS.map((day) => (
                    <option key={day} value={day}>
                      Day {day}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ) : granularity === 'year' ? (
            <input
              type="number"
              className="date-filter__year-input"
              placeholder="YYYY"
              value={realValue}
              onChange={(event) => setRealValue(event.target.value)}
              aria-label="Year"
            />
          ) : (
            <input
              type={granularity === 'day' ? 'date' : 'month'}
              value={realValue}
              onChange={(event) => setRealValue(event.target.value)}
              aria-label={granularity === 'day' ? 'Date' : 'Month'}
            />
          )}
        </>
      )}
    </div>
  )
}

export default DateFilter
