import {
  DAY_OPTIONS,
  MONTH_OPTIONS,
  isoDateToSimDate,
  simDateToIsoDate,
} from './simulationCalendarMath'
import './SimulationDatePicker.css'

export default function SimulationDatePicker({ value, onChange, maxYear = 20 }) {
  const current = value ? isoDateToSimDate(value) : { year: 0, month: 1, day: 1 }

  const update = (patch) => {
    onChange(simDateToIsoDate({ ...current, ...patch }))
  }

  return (
    <div className="sim-date-picker">
      <label>
        Year
        <select value={current.year} onChange={(event) => update({ year: Number(event.target.value) })}>
          {Array.from({ length: maxYear + 1 }, (_, year) => year).map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
      </label>
      <label>
        Month
        <select value={current.month} onChange={(event) => update({ month: Number(event.target.value) })}>
          {MONTH_OPTIONS.map((month) => (
            <option key={month} value={month}>
              {month}
            </option>
          ))}
        </select>
      </label>
      <label>
        Day
        <select value={current.day} onChange={(event) => update({ day: Number(event.target.value) })}>
          {DAY_OPTIONS.map((day) => (
            <option key={day} value={day}>
              {day}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
