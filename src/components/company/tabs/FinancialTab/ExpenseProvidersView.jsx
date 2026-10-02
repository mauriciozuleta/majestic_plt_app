import { useEffect, useState } from 'react'
import { fetchExpenseCategories } from '../../../../services/expenses'
import { createExpenseProvider, fetchExpenseProviders } from '../../../../services/expenseProviders'
import './ExpenseProviders.css'

function AddExpenseProviderModal({ categories, onSave, onCancel }) {
  const [categoryName, setCategoryName] = useState('')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!categoryName || !name.trim()) {
      setError('Choose a category and enter the provider name.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave(categoryName, name.trim())
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <div className="revenue-stream-modal__overlay">
      <div className="revenue-stream-modal">
        <h3>Add Provider</h3>
        <form className="revenue-stream-modal__form" onSubmit={handleSubmit}>
          <label>
            Expense category
            <select value={categoryName} onChange={(event) => setCategoryName(event.target.value)}>
              <option value="">-- Select an expense category --</option>
              {categories.map((item) => (
                <option key={item.id} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Provider name
            <input type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Digicel Business" />
          </label>
          {error && <div className="revenue-stream-modal__error">{error}</div>}
          <div className="revenue-stream-modal__actions">
            <button type="button" className="revenue-stream-modal__cancel" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="revenue-stream-modal__save" disabled={saving}>
              {saving ? 'Saving…' : 'Save Provider'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// COS/Expenses ▸ Providers ▸ Expenses: every expense category that has a
// provider — named on a saved expense (Commercial Operations ▸ Add Expense)
// or added here — with its providers listed underneath.
function ExpenseProvidersView({ companyId }) {
  const [groups, setGroups] = useState([])
  const [categories, setCategories] = useState([])
  const [status, setStatus] = useState('loading')
  const [modalOpen, setModalOpen] = useState(false)

  const reload = () => fetchExpenseProviders(companyId).then(setGroups)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchExpenseProviders(companyId), fetchExpenseCategories().catch(() => [])])
      .then(([nextGroups, nextCategories]) => {
        if (cancelled) return
        setGroups(nextGroups)
        // Percent-of-revenue/profit categories are computed, never paid to anyone.
        setCategories(nextCategories.filter((item) => !item.percent_of_enabled))
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [companyId])

  const handleSave = async (categoryName, name) => {
    await createExpenseProvider(companyId, categoryName, name)
    setModalOpen(false)
    await reload()
  }

  if (status === 'loading') return <p className="air-logistics__empty">Loading providers…</p>
  if (status === 'error') return <p className="air-logistics__error">Could not load the providers.</p>

  return (
    <section className="air-logistics__section">
      <div className="expense-providers__header">
        <div>
          <h4>Expense Providers</h4>
          <p>Providers by expense category — from every expense recorded in Commercial Operations, plus any added here.</p>
        </div>
        <button type="button" className="air-logistics__btn air-logistics__btn--primary" onClick={() => setModalOpen(true)}>
          Add Provider
        </button>
      </div>

      {groups.length === 0 ? (
        <div className="air-logistics__empty">No providers yet — add one, or record an expense with a provider.</div>
      ) : (
        <div className="expense-providers__grid">
          {groups.map((group) => (
            <div key={group.category} className="expense-providers__card">
              <div className="expense-providers__category">{group.category}</div>
              <ul className="expense-providers__list">
                {group.providers.map((provider) => (
                  <li key={provider.name}>
                    <span>{provider.name}</span>
                    <span className="expense-providers__meta">
                      {provider.expense_count > 0
                        ? `${provider.expense_count} expense${provider.expense_count === 1 ? '' : 's'}`
                        : 'added here'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {modalOpen && <AddExpenseProviderModal categories={categories} onSave={handleSave} onCancel={() => setModalOpen(false)} />}
    </section>
  )
}

export default ExpenseProvidersView
