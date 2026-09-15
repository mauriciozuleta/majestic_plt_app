import { Fragment, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { IconLink, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react'
import {
  createStartupInvestmentPlan,
  createStartupInvestmentRecord,
  deleteStartupInvestmentRecord,
  fetchStartupInvestmentPlan,
  fetchStartupInvestmentRecords,
  updateStartupInvestmentLinkToParent,
  updateStartupInvestmentPlan,
  updateStartupInvestmentRecord,
} from '../../../../services/startupInvestment'
import AddStartupRecordModal from './AddStartupRecordModal'
import ExportPdfButton from '../../../shared/PdfExport/ExportPdfButton'
import { CATEGORIES, EXPENSE_CATEGORY_KEYS, WORKING_CAPITAL_KEY, buildStartupInvestmentPdfSpec } from './startupInvestmentPdfSpec'
import { useAppStore } from '../../../../store/useAppStore'
import './StartupInvestmentView.css'

const MONTH_OPTIONS = Array.from({ length: 36 }, (_, index) => index + 1)

function resizeMonths(months, targetLength) {
  if (months.length === targetLength) return months
  if (months.length > targetLength) return months.slice(0, targetLength)
  return [...months, ...new Array(targetLength - months.length).fill(0)]
}

// Companies that name `companyId` as their parent and have "Link to parent
// accounts" checked each contribute one read-only row here, under
// Investment in Subsidiaries, equal to their own EFFECTIVE monthly cash
// requirement — which itself already includes whatever rolled up into them
// from their own linked children (see computeEffectiveMonthlyRequirement
// below), so a grandparent's number here matches what you'd see by adding
// up the child's own tab, not just that child's own directly-entered
// records.
async function computeLinkedRecords(companies, companyId, plan) {
  const childCompanies = companies.filter(
    (item) => item.companyDependency === 'Children' && item.parentCompanyId === companyId,
  )
  if (childCompanies.length === 0) return []

  const contributions = await Promise.all(
    childCompanies.map(async (child) => {
      const childPlan = await fetchStartupInvestmentPlan(child.id)
      if (!childPlan || !childPlan.link_to_parent) return null

      const childMonthly = await computeEffectiveMonthlyRequirement(companies, child.id, childPlan)
      if (!childMonthly) return null

      const months = resizeMonths(childMonthly, plan.pre_operational_months)
      return {
        id: `linked:${child.id}`,
        category: 'investment_subsidiaries',
        name: child.name,
        total_amount: months.reduce((sum, value) => sum + value, 0),
        months,
        isLinked: true,
      }
    }),
  )
  return contributions.filter(Boolean)
}

// A company's own "Monthly cash requirement" (see the tfoot row below),
// but computed for an arbitrary company rather than the one currently
// being viewed — recursive, so it cascades through however many levels of
// "Link to parent accounts" sit beneath it.
async function computeEffectiveMonthlyRequirement(companies, companyId, plan) {
  const records = await fetchStartupInvestmentRecords(companyId)
  const linkedRecords = await computeLinkedRecords(companies, companyId, plan)
  const spec = buildStartupInvestmentPdfSpec(plan, [...records, ...linkedRecords])
  return spec.totalsRow.values
}

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
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === companyId)
  const [plan, setPlan] = useState(null)
  const [records, setRecords] = useState([])
  // Read-only rows contributed by child companies with "Link to parent
  // accounts" checked — never sent to the backend, never editable here.
  const [linkedContributions, setLinkedContributions] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [createError, setCreateError] = useState('')
  const [recordModal, setRecordModal] = useState(null)
  const [isEditingMonths, setIsEditingMonths] = useState(false)
  const [pendingMonths, setPendingMonths] = useState(12)
  const [savingMonths, setSavingMonths] = useState(false)
  const [savingLinkToParent, setSavingLinkToParent] = useState(false)
  const [collapsedCategories, setCollapsedCategories] = useState(() => new Set())
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedRecordIds, setSelectedRecordIds] = useState(() => new Set())
  const [duplicating, setDuplicating] = useState(false)

  const isChildCompany = company?.companyDependency === 'Children' && Boolean(company?.parentCompanyId)

  const toggleCategoryCollapsed = (key) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleSelectionMode = () => {
    setSelectionMode((prev) => !prev)
    setSelectedRecordIds(new Set())
  }

  const toggleRecordSelected = (recordId) => {
    setSelectedRecordIds((prev) => {
      const next = new Set(prev)
      if (next.has(recordId)) next.delete(recordId)
      else next.add(recordId)
      return next
    })
  }

  const reload = async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const nextPlan = await fetchStartupInvestmentPlan(companyId)
      setPlan(nextPlan)
      if (nextPlan) {
        const nextRecords = await fetchStartupInvestmentRecords(companyId)
        setRecords(nextRecords)
        setPendingMonths(nextPlan.pre_operational_months)
        setLinkedContributions(await computeLinkedRecords(companies, companyId, nextPlan))
      } else {
        setLinkedContributions([])
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

  const handleSaveMonths = async () => {
    setSavingMonths(true)
    setError('')
    try {
      await updateStartupInvestmentPlan(companyId, pendingMonths)
      setIsEditingMonths(false)
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingMonths(false)
    }
  }

  const handleSaveRecord = async (payload) => {
    if (recordModal.mode === 'edit') {
      await updateStartupInvestmentRecord(companyId, recordModal.record.id, payload)
    } else {
      await createStartupInvestmentRecord(companyId, payload)
    }
    setRecordModal(null)
    await reload()
  }

  const handleDuplicateSelected = async () => {
    setDuplicating(true)
    setError('')
    try {
      const selectedRecords = records.filter((record) => selectedRecordIds.has(record.id))
      await Promise.all(
        selectedRecords.map((record) =>
          createStartupInvestmentRecord(companyId, {
            category: record.category,
            name: `${record.name} (copy)`,
            description: record.description,
            total_amount: record.total_amount,
            use_installments: record.use_installments,
            months: record.months,
          }),
        ),
      )
      setSelectionMode(false)
      setSelectedRecordIds(new Set())
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setDuplicating(false)
    }
  }

  const handleDeleteRecord = async (record) => {
    if (!window.confirm(`Delete "${record.name}"? This can't be undone.`)) return
    await deleteStartupInvestmentRecord(companyId, record.id)
    await reload()
  }

  const handleToggleLinkToParent = async (checked) => {
    setSavingLinkToParent(true)
    setError('')
    try {
      const updatedPlan = await updateStartupInvestmentLinkToParent(companyId, checked)
      setPlan(updatedPlan)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingLinkToParent(false)
    }
  }

  if (loading) {
    return <div className="startup-investment__status">Loading start-up investment...</div>
  }

  if (!plan) {
    return <CreatePlanModal onCreate={handleCreate} creating={creating} error={createError} />
  }

  const monthCount = plan.pre_operational_months
  const displayRecords = [...records, ...linkedContributions]
  const recordsByCategory = new Map(CATEGORIES.map((category) => [category.key, []]))
  displayRecords.forEach((record) => {
    const list = recordsByCategory.get(record.category)
    if (list) list.push(record)
  })

  const categoryTotals = (key) =>
    (recordsByCategory.get(key) || []).reduce((sum, record) => sum + record.total_amount, 0)

  const categoryMonths = (key) => {
    const totals = new Array(monthCount).fill(0)
    ;(recordsByCategory.get(key) || []).forEach((record) => {
      record.months.forEach((value, index) => {
        totals[index] += value
      })
    })
    return totals
  }

  const totalStartupExpenses = EXPENSE_CATEGORY_KEYS.reduce((sum, key) => sum + categoryTotals(key), 0)
  const totalWorkingCapital = categoryTotals(WORKING_CAPITAL_KEY)
  const totalRequiredInvestment = totalStartupExpenses + totalWorkingCapital

  const monthlyCashRequirement = Array.from({ length: monthCount }, (_, index) =>
    CATEGORIES.reduce((sum, category) => sum + categoryMonths(category.key)[index], 0),
  )

  const activeCategoryKey = recordModal ? (recordModal.mode === 'edit' ? recordModal.record.category : recordModal.category) : null
  const activeCategoryMeta = CATEGORIES.find((category) => category.key === activeCategoryKey)

  const pdfSpec = buildStartupInvestmentPdfSpec(plan, displayRecords)

  return (
    <div className="panel-surface startup-investment">
      <div className="startup-investment__header-row">
        <div className="startup-investment__title-group">
          <h3>Start-up Investment</h3>
          {isChildCompany && (
            <label
              className="startup-investment__link-toggle"
              title="Roll this company's monthly cash requirement into its parent's Investment in Subsidiaries category"
            >
              <input
                type="checkbox"
                checked={Boolean(plan.link_to_parent)}
                disabled={savingLinkToParent}
                onChange={(event) => handleToggleLinkToParent(event.target.checked)}
              />
              Link to parent accounts
            </label>
          )}
        </div>
        <div className="startup-investment__selection-toolbar">
          {selectionMode ? (
            <>
              <span className="startup-investment__selection-count">{selectedRecordIds.size} selected</span>
              <button
                type="button"
                className="startup-investment__btn startup-investment__btn--primary"
                disabled={selectedRecordIds.size === 0 || duplicating}
                onClick={handleDuplicateSelected}
              >
                {duplicating ? 'Duplicating…' : `Duplicate${selectedRecordIds.size > 0 ? ` (${selectedRecordIds.size})` : ''}`}
              </button>
              <button type="button" className="startup-investment__btn" onClick={toggleSelectionMode}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className="startup-investment__btn" onClick={toggleSelectionMode}>
              Duplicate record
            </button>
          )}
        </div>
        <ExportPdfButton spec={pdfSpec} label="Export to PDF" />
      </div>
      <div className="startup-investment__subtitle">
        <p>
          Pre-operational cash requirement over {monthCount} month{monthCount === 1 ? '' : 's'}.
        </p>
        {!isEditingMonths ? (
          <button type="button" className="startup-investment__edit-months-btn" onClick={() => setIsEditingMonths(true)} title="Edit pre-operational months">
            <IconPencil size={14} stroke={1.8} />
          </button>
        ) : (
          <span className="startup-investment__edit-months">
            <select value={pendingMonths} onChange={(event) => setPendingMonths(Number(event.target.value))}>
              {MONTH_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <button type="button" className="startup-investment__btn" onClick={() => setIsEditingMonths(false)} disabled={savingMonths}>
              Cancel
            </button>
            <button
              type="button"
              className="startup-investment__btn startup-investment__btn--primary"
              onClick={handleSaveMonths}
              disabled={savingMonths}
            >
              {savingMonths ? 'Saving…' : 'Save'}
            </button>
          </span>
        )}
      </div>

      <div className="startup-investment__stats">
        <div className="startup-investment__stat-tile">
          <div className="startup-investment__stat-label">Total Start-up Expenses</div>
          <div className="startup-investment__stat-value">${totalStartupExpenses.toLocaleString('en-US')}</div>
        </div>
        <div className="startup-investment__stat-tile">
          <div className="startup-investment__stat-label">Total start-up working capital</div>
          <div className="startup-investment__stat-value">${totalWorkingCapital.toLocaleString('en-US')}</div>
        </div>
        <div className="startup-investment__stat-tile startup-investment__stat-tile--primary">
          <div className="startup-investment__stat-label">Total start-up required investment</div>
          <div className="startup-investment__stat-value">${totalRequiredInvestment.toLocaleString('en-US')}</div>
        </div>
      </div>

      {error && <div className="startup-investment__error">{error}</div>}

      <div className="startup-investment__scroll">
        <table className="startup-investment__table">
          <thead>
            <tr>
              <th className="sticky-col">Category / Record</th>
              {Array.from({ length: monthCount }, (_, index) => (
                <th key={index} className="num">
                  M{index + 1}
                </th>
              ))}
              <th className="num">Total</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {CATEGORIES.map((category) => {
              const categoryRecords = recordsByCategory.get(category.key) || []
              const monthTotals = categoryMonths(category.key)
              const isCollapsed = collapsedCategories.has(category.key)

              return (
                <Fragment key={category.key}>
                  <tr className="startup-investment__category-row">
                    <td className="sticky-col" colSpan={monthCount + 3}>
                      <span className="startup-investment__category-title">
                        <button
                          type="button"
                          className="startup-investment__collapse-toggle"
                          onClick={() => toggleCategoryCollapsed(category.key)}
                          title={isCollapsed ? 'Expand category' : 'Collapse category'}
                        >
                          {isCollapsed ? '▸' : '▾'}
                        </button>
                        <button
                          type="button"
                          className="startup-investment__add-record-icon"
                          onClick={() => setRecordModal({ mode: 'create', category: category.key })}
                          title={`Add ${category.label} record`}
                        >
                          <IconPlus size={13} stroke={2.2} />
                        </button>
                        <span className="startup-investment__category-label" style={{ color: category.color }}>
                          {category.label}
                        </span>
                        <span className="startup-investment__category-tag">
                          {categoryRecords.length} record{categoryRecords.length === 1 ? '' : 's'} · ${categoryTotals(category.key).toLocaleString('en-US')}
                        </span>
                      </span>
                    </td>
                  </tr>

                  {!isCollapsed &&
                    categoryRecords.map((record) => (
                      <tr key={record.id} className={`startup-investment__record-row ${record.isLinked ? 'is-linked' : ''}`}>
                        <td className="sticky-col" title={record.description || (record.isLinked ? `Linked from ${record.name}'s own plan` : undefined)}>
                          <span className="startup-investment__record-cell">
                            {selectionMode && !record.isLinked && (
                              <input
                                type="checkbox"
                                className="startup-investment__record-checkbox"
                                checked={selectedRecordIds.has(record.id)}
                                onChange={() => toggleRecordSelected(record.id)}
                                aria-label={`Select ${record.name} to duplicate`}
                              />
                            )}
                            <span className="startup-investment__record-name">
                              {record.isLinked ? (
                                <span className="startup-investment__linked-name">
                                  <IconLink size={11} stroke={2} className="startup-investment__linked-icon" />
                                  {record.name}
                                </span>
                              ) : (
                                <>
                                  {record.name}
                                  <span className="startup-investment__record-actions">
                                    <button
                                      type="button"
                                      className="startup-investment__edit-record"
                                      title="Edit this record"
                                      onClick={() => setRecordModal({ mode: 'edit', record })}
                                    >
                                      <IconPencil size={12} stroke={2} />
                                    </button>
                                    <button
                                      type="button"
                                      className="startup-investment__remove"
                                      title="Remove this record"
                                      onClick={() => handleDeleteRecord(record)}
                                    >
                                      <IconTrash size={12} stroke={2} />
                                    </button>
                                  </span>
                                </>
                              )}
                            </span>
                          </span>
                        </td>
                        {record.months.map((value, index) => (
                          <td key={index} className="num">
                            ${value.toLocaleString('en-US')}
                          </td>
                        ))}
                        <td className="num">${record.total_amount.toLocaleString('en-US')}</td>
                        <td />
                      </tr>
                    ))}

                  <tr className="startup-investment__subtotal-row">
                    <td className="sticky-col" style={{ color: category.color }}>
                      {category.label} — subtotal
                    </td>
                    {monthTotals.map((value, index) => (
                      <td key={index} className="num" style={{ color: category.color }}>
                        ${value.toLocaleString('en-US')}
                      </td>
                    ))}
                    <td className="num" style={{ color: category.color }}>
                      ${categoryTotals(category.key).toLocaleString('en-US')}
                    </td>
                    <td />
                  </tr>
                </Fragment>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="startup-investment__total-row">
              <td className="sticky-col">Monthly cash requirement</td>
              {monthlyCashRequirement.map((value, index) => (
                <td key={index} className="num">
                  ${value.toLocaleString('en-US')}
                </td>
              ))}
              <td className="num">${monthlyCashRequirement.reduce((sum, value) => sum + value, 0).toLocaleString('en-US')}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      {recordModal && (
        <AddStartupRecordModal
          category={activeCategoryKey}
          categoryLabel={activeCategoryMeta?.label ?? ''}
          monthCount={monthCount}
          initialRecord={recordModal.mode === 'edit' ? recordModal.record : null}
          onSave={handleSaveRecord}
          onCancel={() => setRecordModal(null)}
        />
      )}
    </div>
  )
}

export default StartupInvestmentView
