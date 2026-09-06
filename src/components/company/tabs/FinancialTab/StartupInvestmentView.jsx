import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createStartupInvestmentPlan,
  fetchStartupInvestmentEntries,
  fetchStartupInvestmentPlan,
  saveStartupInvestmentEntry,
} from '../../../../services/startupInvestment'
import './StartupInvestmentView.css'

const CATEGORIES = [
  { key: 'assets_acquisition', label: 'Start-up Assets Acquisition' },
  { key: 'other_assets_purchases', label: 'Other assets Purchases' },
  { key: 'startup_expenses', label: 'Start-up Expenses' },
  { key: 'startup_payroll', label: 'Start-up development payroll' },
  { key: 'working_capital', label: 'Start-up Working capital requirement' },
]
const EXPENSE_CATEGORY_KEYS = ['assets_acquisition', 'other_assets_purchases', 'startup_expenses', 'startup_payroll']
const WORKING_CAPITAL_KEY = 'working_capital'
const MONTH_OPTIONS = Array.from({ length: 36 }, (_, index) => index + 1)

function CreatePlanModal({ onCreate, creating, error }) {
  const [months, setMonths] = useState(12)

  return (
    <div className="startup-investment-modal__overlay">
      <div className="startup-investment-modal">
        <h3>Start-up Investment</h3>
        <p>No start-up investment plan yet for this company.</p>
        <label className="startup-investment-modal__field">
          Pre-operational Project development time in months:
          <select value={months} onChange={(event) => setMonths(Number(event.target.value))}>
            {MONTH_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        {error && <div className="startup-investment-modal__error">{error}</div>}
        <div className="startup-investment-modal__actions">
          <button type="button" className="startup-investment-modal__create" onClick={() => onCreate(months)} disabled={creating}>
            {creating ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

function StartupInvestmentView() {
  const { companyId } = useParams()
  const [plan, setPlan] = useState(null)
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [createError, setCreateError] = useState('')
  const [drafts, setDrafts] = useState(() => new Map())

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const nextPlan = await fetchStartupInvestmentPlan(companyId)
      setPlan(nextPlan)
      if (nextPlan) {
        const nextEntries = await fetchStartupInvestmentEntries(companyId)
        setEntries(nextEntries)
        setDrafts(new Map())
      }
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

  const handleCreate = async (months) => {
    setCreating(true)
    setCreateError('')
    try {
      await createStartupInvestmentPlan(companyId, months)
      await reload()
    } catch (err) {
      setCreateError(err.message)
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return <div className="startup-investment__status">Loading start-up investment...</div>
  }

  if (!plan) {
    return <CreatePlanModal onCreate={handleCreate} creating={creating} error={createError} />
  }

  const monthCount = plan.pre_operational_months
  const entriesByCategory = new Map(entries.map((entry) => [entry.category, entry.months]))

  const displayMonths = (category) => drafts.get(category) || entriesByCategory.get(category) || new Array(monthCount).fill(0)

  const rowTotal = (category) => displayMonths(category).reduce((sum, value) => sum + (Number(value) || 0), 0)

  const totalStartupExpenses = EXPENSE_CATEGORY_KEYS.reduce((sum, key) => sum + rowTotal(key), 0)
  const totalWorkingCapital = rowTotal(WORKING_CAPITAL_KEY)
  const totalRequiredInvestment = totalStartupExpenses + totalWorkingCapital

  const monthlyCashRequirement = Array.from({ length: monthCount }, (_, index) =>
    CATEGORIES.reduce((sum, category) => sum + (Number(displayMonths(category.key)[index]) || 0), 0),
  )

  const draftCount = drafts.size

  const handleDraftMonthChange = (category, monthIndex, value, currentMonths) => {
    setDrafts((prev) => {
      const next = new Map(prev)
      const base = next.get(category) || [...currentMonths]
      const updated = [...base]
      updated[monthIndex] = value
      next.set(category, updated)
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      for (const [category, months] of drafts.entries()) {
        // eslint-disable-next-line no-await-in-loop
        await saveStartupInvestmentEntry(companyId, category, months)
      }
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDiscard = () => setDrafts(new Map())

  return (
    <div className="panel-surface startup-investment">
      <h3>Start-up Investment</h3>
      <p>Pre-operational cash requirement over {monthCount} month{monthCount === 1 ? '' : 's'}.</p>

      <div className="startup-investment__stats">
        <div className="startup-investment__stat-tile">
          <div className="startup-investment__stat-label">Total Start-up Expenses</div>
          <div className="startup-investment__stat-value">${totalStartupExpenses.toLocaleString()}</div>
        </div>
        <div className="startup-investment__stat-tile">
          <div className="startup-investment__stat-label">Total start-up working capital</div>
          <div className="startup-investment__stat-value">${totalWorkingCapital.toLocaleString()}</div>
        </div>
        <div className="startup-investment__stat-tile startup-investment__stat-tile--primary">
          <div className="startup-investment__stat-label">Total start-up required investment</div>
          <div className="startup-investment__stat-value">${totalRequiredInvestment.toLocaleString()}</div>
        </div>
      </div>

      {draftCount > 0 && (
        <div className="startup-investment__draft-bar">
          <span>
            {draftCount} unsaved change{draftCount === 1 ? '' : 's'}
          </span>
          <span className="startup-investment__draft-actions">
            <button type="button" className="startup-investment__btn" onClick={handleDiscard} disabled={saving}>
              Discard
            </button>
            <button type="button" className="startup-investment__btn startup-investment__btn--primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : `Save ${draftCount} change${draftCount === 1 ? '' : 's'}`}
            </button>
          </span>
        </div>
      )}

      {error && <div className="startup-investment__error">{error}</div>}

      <div className="startup-investment__scroll">
        <table className="startup-investment__table">
          <thead>
            <tr>
              <th className="sticky-col">Category</th>
              {Array.from({ length: monthCount }, (_, index) => (
                <th key={index} className="num">
                  M{index + 1}
                </th>
              ))}
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {CATEGORIES.map((category) => {
              const draft = drafts.get(category.key) || null
              const months = displayMonths(category.key)

              return (
                <tr key={category.key}>
                  <td className="sticky-col">{category.label}</td>
                  {months.map((value, index) => (
                    <td key={index} className="num">
                      <input
                        type="number"
                        className={`startup-investment__month-input ${draft ? 'is-dirty' : ''}`}
                        value={value}
                        onChange={(event) => {
                          const next = Number(event.target.value)
                          handleDraftMonthChange(category.key, index, Number.isFinite(next) ? next : 0, entriesByCategory.get(category.key) || months)
                        }}
                      />
                    </td>
                  ))}
                  <td className="num">${rowTotal(category.key).toLocaleString()}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="startup-investment__total-row">
              <td className="sticky-col">Monthly cash requirement</td>
              {monthlyCashRequirement.map((value, index) => (
                <td key={index} className="num">
                  ${value.toLocaleString()}
                </td>
              ))}
              <td className="num">${monthlyCashRequirement.reduce((sum, value) => sum + value, 0).toLocaleString()}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

export default StartupInvestmentView
