import { IconEdit } from '@tabler/icons-react'
import { CATEGORIES } from './categories'

function DayView({ dayEntries, onDeleteEntry, onEditEntry }) {
  return (
    <div className="commercial-ops-day">
      {CATEGORIES.map((category) => {
        const entries = dayEntries.filter((entry) => entry.category === category.key)
        const total = entries.reduce((sum, entry) => sum + entry.amount, 0)

        return (
          <div className="commercial-ops-day__section" key={category.key}>
            <div className="commercial-ops-day__section-header">
              <span className="commercial-ops-day__category" style={{ borderColor: category.color, color: category.color }}>
                {category.label}
              </span>
              <span className="commercial-ops-day__total">${total.toLocaleString()}</span>
            </div>

            {entries.length === 0 ? (
              <div className="commercial-ops-day__empty">No {category.label.toLowerCase()} entries for this day.</div>
            ) : (
              <ul className="commercial-ops-day__list">
                {entries.map((entry) => (
                  <li key={entry.id} className="commercial-ops-day__entry">
                    <span className="commercial-ops-day__entry-description">
                      {category.key === 'revenue'
                        ? [entry.entry_type, entry.client].filter(Boolean).join(' — ') || '—'
                        : entry.description || '—'}
                    </span>
                    <span className="commercial-ops-day__entry-amount">${entry.amount.toLocaleString()}</span>
                    <button
                      type="button"
                      className="commercial-ops-day__edit"
                      title="Edit this entry"
                      onClick={() => onEditEntry(entry)}
                    >
                      <IconEdit size={14} stroke={1.8} />
                    </button>
                    <button
                      type="button"
                      className="commercial-ops-day__remove"
                      title="Remove this entry"
                      onClick={() => onDeleteEntry(entry.id)}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default DayView
