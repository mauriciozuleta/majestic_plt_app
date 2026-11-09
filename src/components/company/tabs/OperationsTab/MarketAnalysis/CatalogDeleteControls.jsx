import { useCallback, useState } from 'react'
import { deleteCatalogProducts } from '../../../../../services/catalogProducts'
import { useAppStore } from '../../../../../store/useAppStore'
import './CatalogDeleteControls.css'

// The row selection of a portfolio table: the set of row keys that are ticked.
export function useCatalogSelection() {
  const [selected, setSelected] = useState(() => new Set())
  const toggle = useCallback((key) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])
  const setMany = useCallback((keys, on) => {
    setSelected((previous) => {
      const next = new Set(previous)
      keys.forEach((key) => (on ? next.add(key) : next.delete(key)))
      return next
    })
  }, [])
  const clear = useCallback(() => setSelected(new Set()), [])
  return { selected, toggle, setMany, clear }
}

export function RowCheckbox({ selection, rowKey, label }) {
  return (
    <input
      type="checkbox"
      className="catalog-select__box"
      checked={selection.selected.has(rowKey)}
      onChange={() => selection.toggle(rowKey)}
      aria-label={`Select ${label}`}
    />
  )
}

// Header checkbox: ticks / unticks every row that is currently listed (after the table's own filters).
export function SelectAllCheckbox({ selection, rowKeys }) {
  const ticked = rowKeys.filter((key) => selection.selected.has(key)).length
  return (
    <input
      type="checkbox"
      className="catalog-select__box"
      checked={rowKeys.length > 0 && ticked === rowKeys.length}
      ref={(element) => {
        if (element) element.indeterminate = ticked > 0 && ticked < rowKeys.length
      }}
      onChange={(event) => selection.setMany(rowKeys, event.target.checked)}
      aria-label="Select all the listed products"
    />
  )
}

// The red "Delete X products" button (only while something is ticked) and its confirmation. `describe()` returns [{ item, label }] for the ticked rows:
// `item` is what the backend deletes (one item, or a list when a row lives in several sources), `label` what the confirmation lists. `onDeleted` runs after the database was changed (reload the table there).
export function DeleteSelectedButton({ selection, describe, onDeleted }) {
  const currentUser = useAppStore((state) => state.currentUser)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(null)
  const count = selection.selected.size

  if (count === 0 && !done) return null
  const noun = count === 1 ? 'product' : 'products'
  const rows = confirming ? describe() : []

  const handleConfirm = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await deleteCatalogProducts(rows.flatMap((row) => row.item), currentUser?.name)
      selection.clear()
      setConfirming(false)
      setDone(result)
      await onDeleted?.(result)
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {count > 0 && (
        <button
          type="button"
          className="catalog-select__delete"
          onClick={() => {
            setError('')
            setConfirming(true)
          }}
        >
          Delete {count} {noun}
        </button>
      )}
      {done && count === 0 && (
        <span className="catalog-select__done" role="status">
          {done.removed} {done.removed === 1 ? 'product' : 'products'} deleted — report saved in Documentation ▸ Modification Reports.{' '}
          <button type="button" className="catalog-select__dismiss" onClick={() => setDone(null)} aria-label="Dismiss">
            ×
          </button>
        </span>
      )}
      {confirming && (
        <div className="catalog-select__overlay" role="dialog" aria-modal="true" aria-label="Confirm deletion">
          <div className="catalog-select__dialog">
            <h3>
              Delete {count} {noun}?
            </h3>
            <p>
              {count === 1 ? 'This product' : 'These products'} will be removed from the database. A modification report will be saved in Documentation.
              Updating a source from its website can bring products back.
            </p>
            <ul className="catalog-select__list">
              {rows.slice(0, 12).map((row, index) => (
                <li key={index}>{row.label}</li>
              ))}
            </ul>
            {rows.length > 12 && <p className="catalog-select__more">…and {rows.length - 12} more</p>}
            {error && <p className="catalog-select__error">{error}</p>}
            <div className="catalog-select__actions">
              <button type="button" onClick={() => setConfirming(false)} disabled={busy}>
                Cancel
              </button>
              <button type="button" className="catalog-select__delete" onClick={handleConfirm} disabled={busy}>
                {busy ? 'Deleting…' : `Delete ${count} ${noun}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
