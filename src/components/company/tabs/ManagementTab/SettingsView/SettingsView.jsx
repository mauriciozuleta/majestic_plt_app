import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IconX } from '@tabler/icons-react'
import RoadmapDateInput from '../RoadmapView/RoadmapDateInput'
import PayrollLevelsModal from './PayrollLevelsModal'
import MarketOpportunitySettingsCard from './MarketOpportunitySettingsCard'
import ProductSourcesCard from './ProductSourcesCard'
import DevelopmentPhasesPanel from './DevelopmentPhasesPanel'
import USPayrollTaxPanel from './USPayrollTaxPanel'
import PayrollSchedulePanel from './PayrollSchedulePanel'
import USBenefitsPanel from './USBenefitsPanel'
import MacroeconomicsPanel from './MacroeconomicsPanel'
import StMaartenPayrollTaxPanel from './StMaartenPayrollTaxPanel'
import ColombiaPayrollTaxPanel from './ColombiaPayrollTaxPanel'
import { deleteCompany } from '../../../../../services/companies'
import { broadcastCompanyDataChange } from '../../../../../services/companyDataSync'
import { fetchCommercialCountries } from '../../../../../services/commercialStructure'
import {
  createExpenseCategory,
  deleteExpenseCategory,
  fetchExpenseCategories,
  fetchExpenseCategoryCompanySettings,
  renameExpenseCategory,
  setExpenseCategoryCompanySetting,
} from '../../../../../services/expenses'
import { fetchSettings, updateCalendarMode, updateEnabledBenefits, updateTimeProjection } from '../../../../../services/settings'
import { useAppStore } from '../../../../../store/useAppStore'
import './SettingsView.css'

// These three are computed live from Payroll data and overlaid onto the
// Expenses tab by exact name match — renaming them here would break that
// overlay, so they're shown read-only.
const PROTECTED_EXPENSE_CATEGORY_NAMES = new Set(['Payroll', 'Payroll Tax Expense', 'Employee Benefits'])

// "Net Profit" here specifically means Net Profit computed BEFORE any
// percent-of-X category (including itself) — see ExpensesView.jsx's own
// comment on this for why: Net Profit already subtracts every expense, so a
// category that's itself a percentage of Net Profit can't be included in
// that subtraction without becoming circular.
const PERCENT_OF_METRICS = [
  { key: 'gross_revenue', label: 'Gross Revenue' },
  { key: 'net_profit', label: 'Net Profit' },
]

// Not wired up yet — these are placeholder pills for a future tax/macro
// module, listed under each country in the commercial structure.
// "Macroeconomics" is where per-country inflation will eventually live,
// replacing the flat "default raise" control that used to be in Payroll.
const TAX_CATEGORIES = [
  'Income Taxes',
  'Export Taxes',
  'Import Taxes',
  'Payroll taxes/charges',
  'Payroll Schedule',
  'Macroeconomics',
  'Benefits',
]
// Which pills are actually wired, per country — both panels read/write the
// same `enabledBenefitKeys` state below, so enabling a benefit here
// immediately shows up in the Salary Calculator's numbers too. Payroll
// Schedule is portfolio-wide (not actually US-specific), but it only ever
// had a home under United States' pills, so it stays there as its own
// pill rather than introducing a new place to look for it.
const WIRED_PILLS_BY_COUNTRY = {
  'United States': {
    'Payroll taxes/charges': USPayrollTaxPanel,
    'Payroll Schedule': PayrollSchedulePanel,
    Benefits: USBenefitsPanel,
    Macroeconomics: MacroeconomicsPanel,
  },
  // The commercial-structure entry here is labeled "Saint Martin (French
  // part)" but its data (currency ANG) is actually Dutch Sint Maarten's —
  // there's no separate correctly-labeled entry in the reference country
  // catalog. This wires the Dutch-side (SZV) structure the user asked for
  // ("St Marteen") to the closest existing country row.
  'Saint Martin (French part)': {
    'Payroll taxes/charges': StMaartenPayrollTaxPanel,
    Macroeconomics: MacroeconomicsPanel,
  },
  Colombia: {
    'Payroll taxes/charges': ColombiaPayrollTaxPanel,
    Macroeconomics: MacroeconomicsPanel,
  },
}

function SettingsView() {
  const navigate = useNavigate()
  const companies = useAppStore((state) => state.companies)
  const removeCompany = useAppStore((state) => state.removeCompany)
  const [calendarMode, setCalendarMode] = useState('real')
  const [projectionYears, setProjectionYears] = useState(5)
  const [pendingRealStartDate, setPendingRealStartDate] = useState(new Date().toISOString().slice(0, 10))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectedCompanyId, setSelectedCompanyId] = useState('')
  const [message, setMessage] = useState('')
  const [messageType, setMessageType] = useState('info')
  const [isPayrollLevelsModalOpen, setPayrollLevelsModalOpen] = useState(false)
  const [taxCountries, setTaxCountries] = useState([])
  const [taxCountriesStatus, setTaxCountriesStatus] = useState('loading')
  const [expandedTaxCountryIds, setExpandedTaxCountryIds] = useState(() => new Set())
  const [expandedTaxPillKeys, setExpandedTaxPillKeys] = useState(() => new Set())
  const [enabledBenefitKeys, setEnabledBenefitKeys] = useState([])
  const [expenseCategories, setExpenseCategories] = useState([])
  const [expenseCategoriesStatus, setExpenseCategoriesStatus] = useState('loading')
  const [expenseNameDrafts, setExpenseNameDrafts] = useState({})
  // Keyed by `${categoryId}::${companyId}` -> { excluded, percentValue }.
  // originalCompanySettingDrafts is a snapshot of what's actually saved, so
  // "Save changes" only ever writes the (category, company) pairs that
  // actually changed instead of rewriting everything every time.
  const [companySettingDrafts, setCompanySettingDrafts] = useState({})
  const [originalCompanySettingDrafts, setOriginalCompanySettingDrafts] = useState({})
  // Keyed by categoryId -> { enabled, metric } — the row-level "% of"
  // checkbox + metric dropdown, staged the same way expenseNameDrafts is.
  const [expensePercentDrafts, setExpensePercentDrafts] = useState({})
  const [pendingNewExpenseCategories, setPendingNewExpenseCategories] = useState([])
  const [pendingDeletedExpenseCategoryIds, setPendingDeletedExpenseCategoryIds] = useState(() => new Set())
  const [isAddingExpenseCategory, setIsAddingExpenseCategory] = useState(false)
  const [newExpenseCategoryName, setNewExpenseCategoryName] = useState('')
  const [expenseSettingsSaving, setExpenseSettingsSaving] = useState(false)
  const [expenseSettingsMessage, setExpenseSettingsMessage] = useState('')
  const [expenseSettingsMessageType, setExpenseSettingsMessageType] = useState('info')
  const [isExpensesCardExpanded, setIsExpensesCardExpanded] = useState(false)
  const [isTaxStructureCardExpanded, setIsTaxStructureCardExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchSettings()
      .then((settings) => {
        if (!cancelled) {
          setCalendarMode(settings.calendar_mode ?? 'real')
          setProjectionYears(Math.max(5, Math.min(10, Number(settings.projection_years ?? 5))))
          setEnabledBenefitKeys(Array.isArray(settings.enabled_benefits) ? settings.enabled_benefits : [])
          setMessage('')
          setMessageType('info')
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setMessage(error.message)
          setMessageType('error')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!companies.length) {
      setTaxCountries([])
      setTaxCountriesStatus('ready')
      return undefined
    }

    let cancelled = false
    setTaxCountriesStatus('loading')

    Promise.all(
      companies.map((company) =>
        fetchCommercialCountries(company.id)
          .then((countries) => countries.map((country) => ({ ...country, companyId: company.id, companyName: company.name })))
          .catch(() => []),
      ),
    ).then((perCompany) => {
      if (cancelled) return
      setTaxCountries(perCompany.flat())
      setTaxCountriesStatus('ready')
    })

    return () => {
      cancelled = true
    }
  }, [companies])

  const toggleTaxCountry = (countryId) => {
    setExpandedTaxCountryIds((prev) => {
      const next = new Set(prev)
      if (next.has(countryId)) next.delete(countryId)
      else next.add(countryId)
      return next
    })
  }

  const toggleTaxPill = (pillKey) => {
    setExpandedTaxPillKeys((prev) => {
      const next = new Set(prev)
      if (next.has(pillKey)) next.delete(pillKey)
      else next.add(pillKey)
      return next
    })
  }

  useEffect(() => {
    let cancelled = false
    setExpenseCategoriesStatus('loading')

    Promise.all([fetchExpenseCategories(), fetchExpenseCategoryCompanySettings()])
      .then(([categories, companySettings]) => {
        if (cancelled) return
        const settingsMap = {}
        companySettings.forEach((row) => {
          settingsMap[`${row.category_id}::${row.company_id}`] = { excluded: row.excluded, percentValue: row.percent_value ?? null }
        })
        setExpenseCategories(categories)
        setCompanySettingDrafts(settingsMap)
        setOriginalCompanySettingDrafts(settingsMap)
        setExpensePercentDrafts({})
        setExpenseCategoriesStatus('ready')
      })
      .catch((error) => {
        if (cancelled) return
        setExpenseSettingsMessage(error.message || 'Failed to load expense settings.')
        setExpenseSettingsMessageType('error')
        setExpenseCategoriesStatus('ready')
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Renames, deletes, additions, and applicability checkboxes are all staged
  // locally — nothing hits the backend until "Save changes" is clicked, so a
  // mistaken edit/delete can be discarded just by not saving.
  const expenseRows = useMemo(
    () => [
      ...expenseCategories
        .filter((category) => !pendingDeletedExpenseCategoryIds.has(category.id))
        .map((category) => ({
          id: category.id,
          name: category.name,
          isNew: false,
          percentOfEnabled: category.percent_of_enabled,
          percentOfMetric: category.percent_of_metric,
        })),
      ...pendingNewExpenseCategories.map((pending) => ({
        id: pending.tempId,
        name: pending.name,
        isNew: true,
        percentOfEnabled: false,
        percentOfMetric: null,
      })),
    ],
    [expenseCategories, pendingDeletedExpenseCategoryIds, pendingNewExpenseCategories],
  )

  const percentDraftFor = (row) => expensePercentDrafts[row.id] ?? { enabled: row.percentOfEnabled, metric: row.percentOfMetric ?? 'gross_revenue' }

  const companySettingDraftFor = (categoryId, companyId) =>
    companySettingDrafts[`${categoryId}::${companyId}`] ?? { excluded: false, percentValue: null }

  const expenseSettingsDirty = useMemo(() => {
    if (pendingNewExpenseCategories.length > 0 || pendingDeletedExpenseCategoryIds.size > 0) return true

    const renamed = expenseCategories.some((category) => {
      if (pendingDeletedExpenseCategoryIds.has(category.id)) return false
      const draft = (expenseNameDrafts[category.id] ?? category.name).trim()
      return draft !== category.name
    })
    if (renamed) return true

    const percentChanged = expenseCategories.some((category) => {
      if (pendingDeletedExpenseCategoryIds.has(category.id)) return false
      const draft = expensePercentDrafts[category.id]
      if (!draft) return false
      return draft.enabled !== category.percent_of_enabled || (draft.enabled && draft.metric !== category.percent_of_metric)
    })
    if (percentChanged) return true

    const allKeys = new Set([...Object.keys(companySettingDrafts), ...Object.keys(originalCompanySettingDrafts)])
    for (const key of allKeys) {
      const draft = companySettingDrafts[key] ?? { excluded: false, percentValue: null }
      const original = originalCompanySettingDrafts[key] ?? { excluded: false, percentValue: null }
      if (draft.excluded !== original.excluded || draft.percentValue !== original.percentValue) return true
    }
    return false
  }, [
    expenseCategories,
    expenseNameDrafts,
    expensePercentDrafts,
    companySettingDrafts,
    originalCompanySettingDrafts,
    pendingNewExpenseCategories,
    pendingDeletedExpenseCategoryIds,
  ])

  const handleExpenseNameDraftChange = (rowId, value) => {
    setExpenseNameDrafts((prev) => ({ ...prev, [rowId]: value }))
  }

  const handleExpenseNameBlur = (row) => {
    const draft = (expenseNameDrafts[row.id] ?? row.name).trim()
    setExpenseNameDrafts((prev) => ({ ...prev, [row.id]: draft || row.name }))
  }

  // wasChecked is the checkbox's state BEFORE this click (not the new one)
  // — since a click always flips it, "was checked" is exactly the new
  // excluded value. Pass the already-negated new-checked value here instead
  // and this silently becomes a no-op (excluded keeps resolving back to
  // whatever it already was).
  const handleToggleExpenseApplicability = (categoryId, companyId, wasChecked) => {
    const key = `${categoryId}::${companyId}`
    setCompanySettingDrafts((prev) => ({
      ...prev,
      [key]: { ...companySettingDraftFor(categoryId, companyId), excluded: wasChecked },
    }))
  }

  const handleChangeCompanyPercentValue = (categoryId, companyId, rawValue) => {
    const key = `${categoryId}::${companyId}`
    const percentValue = rawValue === '' ? null : Number(rawValue)
    setCompanySettingDrafts((prev) => ({
      ...prev,
      [key]: { ...companySettingDraftFor(categoryId, companyId), percentValue },
    }))
  }

  const handleTogglePercentOf = (row, enabled) => {
    setExpensePercentDrafts((prev) => ({
      ...prev,
      [row.id]: { ...percentDraftFor(row), enabled },
    }))
  }

  const handleChangePercentMetric = (row, metric) => {
    setExpensePercentDrafts((prev) => ({
      ...prev,
      [row.id]: { ...percentDraftFor(row), metric },
    }))
  }

  const handleAddExpenseCategoryClick = () => {
    setIsAddingExpenseCategory(true)
    setNewExpenseCategoryName('')
  }

  const handleCancelNewExpenseCategory = () => {
    setIsAddingExpenseCategory(false)
    setNewExpenseCategoryName('')
  }

  const handleSaveNewExpenseCategory = () => {
    const trimmed = newExpenseCategoryName.trim()
    if (!trimmed) return
    if (PROTECTED_EXPENSE_CATEGORY_NAMES.has(trimmed)) {
      setExpenseSettingsMessage(`"${trimmed}" is a reserved name.`)
      setExpenseSettingsMessageType('error')
      return
    }

    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setPendingNewExpenseCategories((prev) => [...prev, { tempId, name: trimmed }])
    setIsAddingExpenseCategory(false)
    setNewExpenseCategoryName('')
    setExpenseSettingsMessage('')
  }

  const handleDeleteExpenseRow = (row) => {
    if (row.isNew) {
      setPendingNewExpenseCategories((prev) => prev.filter((item) => item.tempId !== row.id))
      return
    }
    if (!window.confirm(`Delete "${row.name}"? This won't apply until you click "Save changes".`)) return
    setPendingDeletedExpenseCategoryIds((prev) => {
      const next = new Set(prev)
      next.add(row.id)
      return next
    })
  }

  const handleSaveExpenseChanges = async () => {
    setExpenseSettingsSaving(true)
    setExpenseSettingsMessage('')

    try {
      const tempIdToRealId = {}
      for (const pending of pendingNewExpenseCategories) {
        const name = (expenseNameDrafts[pending.tempId] ?? pending.name).trim() || pending.name
        const created = await createExpenseCategory(name)
        tempIdToRealId[pending.tempId] = created.id
        const percentDraft = expensePercentDrafts[pending.tempId]
        if (percentDraft?.enabled) {
          await renameExpenseCategory(created.id, name, true, percentDraft.metric)
        }
      }

      for (const categoryId of pendingDeletedExpenseCategoryIds) {
        await deleteExpenseCategory(categoryId)
      }

      for (const category of expenseCategories) {
        if (pendingDeletedExpenseCategoryIds.has(category.id)) continue
        const draftName = (expenseNameDrafts[category.id] ?? category.name).trim()
        const percentDraft = percentDraftFor({ id: category.id, percentOfEnabled: category.percent_of_enabled, percentOfMetric: category.percent_of_metric })
        const nameChanged = draftName && draftName !== category.name
        const percentChanged =
          percentDraft.enabled !== category.percent_of_enabled || (percentDraft.enabled && percentDraft.metric !== category.percent_of_metric)
        if (nameChanged || percentChanged) {
          await renameExpenseCategory(category.id, draftName || category.name, percentDraft.enabled, percentDraft.enabled ? percentDraft.metric : null)
        }
      }

      const survivingCategoryIds = [
        ...expenseCategories.filter((category) => !pendingDeletedExpenseCategoryIds.has(category.id)).map((category) => category.id),
        ...Object.values(tempIdToRealId),
      ]
      const realIdToDraftId = new Map(Object.entries(tempIdToRealId).map(([tempId, realId]) => [realId, tempId]))

      for (const categoryId of survivingCategoryIds) {
        const draftId = realIdToDraftId.get(categoryId) ?? categoryId
        for (const company of companies) {
          const key = `${draftId}::${company.id}`
          const draft = companySettingDrafts[key]
          const original = originalCompanySettingDrafts[`${categoryId}::${company.id}`] ?? { excluded: false, percentValue: null }
          if (!draft) continue
          if (draft.excluded !== original.excluded || draft.percentValue !== original.percentValue) {
            await setExpenseCategoryCompanySetting(categoryId, company.id, draft.excluded, draft.percentValue)
          }
        }
      }

      const [categories, companySettings] = await Promise.all([fetchExpenseCategories(), fetchExpenseCategoryCompanySettings()])
      const freshSettingsMap = {}
      companySettings.forEach((row) => {
        freshSettingsMap[`${row.category_id}::${row.company_id}`] = { excluded: row.excluded, percentValue: row.percent_value ?? null }
      })
      setExpenseCategories(categories)
      setCompanySettingDrafts(freshSettingsMap)
      setOriginalCompanySettingDrafts(freshSettingsMap)
      setExpensePercentDrafts({})
      setExpenseNameDrafts({})
      setPendingNewExpenseCategories([])
      setPendingDeletedExpenseCategoryIds(new Set())
      setExpenseSettingsMessage('Saved.')
      setExpenseSettingsMessageType('success')
    } catch (error) {
      setExpenseSettingsMessage(error.message || 'Failed to save expense changes.')
      setExpenseSettingsMessageType('error')
    } finally {
      setExpenseSettingsSaving(false)
    }
  }

  const handleToggleBenefit = async (benefitKey) => {
    const wasEnabled = enabledBenefitKeys.includes(benefitKey)
    const next = wasEnabled ? enabledBenefitKeys.filter((key) => key !== benefitKey) : [...enabledBenefitKeys, benefitKey]
    setEnabledBenefitKeys(next)
    try {
      await updateEnabledBenefits(next)
      companies.forEach((company) => broadcastCompanyDataChange(company.id, 'settings:enabled-benefits-changed'))
    } catch (error) {
      setEnabledBenefitKeys(enabledBenefitKeys)
      setMessage(error.message || 'Failed to update benefits.')
      setMessageType('error')
    }
  }

  useEffect(() => {
    if (!companies.length) {
      setSelectedCompanyId('')
      return
    }

    setSelectedCompanyId((currentSelected) => {
      if (companies.some((company) => company.id === currentSelected)) {
        return currentSelected
      }

      return companies[0].id
    })
  }, [companies])

  const selectedCompany = useMemo(
    () => companies.find((company) => company.id === selectedCompanyId) ?? null,
    [companies, selectedCompanyId],
  )

  const handleModeChange = async (nextMode) => {
    if (nextMode === calendarMode) return

    if (!pendingRealStartDate) {
      setMessage('Pick a reference date before changing calendar mode.')
      setMessageType('error')
      return
    }

    const actionLabel = nextMode === 'simulation' ? 'switch to Simulation' : 'switch back to Real'
    const confirmed = window.confirm(
      `Confirm ${actionLabel} mode? This will convert and save all roadmap and payroll dates using ${pendingRealStartDate} as the reference date.`,
    )

    if (!confirmed) return

    setSaving(true)
    setMessage('')
    setMessageType('info')

    try {
      const result = await updateCalendarMode(nextMode, pendingRealStartDate)
      const taskCount = result.tasks_converted ?? 0
      const payrollCount = result.payroll_records_converted ?? 0

      setCalendarMode(result.calendar_mode ?? nextMode)
      setMessage(`Saved. Converted ${taskCount} roadmap tasks and ${payrollCount} payroll start dates.`)
      setMessageType('success')

      companies.forEach((company) => {
        broadcastCompanyDataChange(company.id, 'settings:calendar-mode-changed')
      })
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const handleProjectionYearsChange = async (value) => {
    const nextValue = Number(value)
    if (Number.isNaN(nextValue)) return
    if (nextValue === projectionYears) return

    setSaving(true)
    setMessage('')
    setMessageType('info')

    try {
      const result = await updateTimeProjection(nextValue)
      const nextProjection = Math.max(5, Math.min(10, Number(result.projection_years ?? nextValue)))
      setProjectionYears(nextProjection)
      setMessage(`Saved. Time projection set to ${nextProjection} years.`)
      setMessageType('success')

      companies.forEach((company) => {
        broadcastCompanyDataChange(company.id, 'settings:projection-years-changed')
      })
    } catch (error) {
      setMessage(error.message)
      setMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="settings-view__status">Loading settings...</div>
  }

  return (
    <section className="settings-view">
      <header className="settings-view__header">
        <h4>Settings</h4>
        <p>Controls here apply to the whole app, not just management.</p>
      </header>

      <div className="settings-view__card">
        <label>
          Calendar mode
          <select value={calendarMode} onChange={(event) => handleModeChange(event.target.value)} disabled={saving}>
            <option value="real">Real</option>
            <option value="simulation">Simulation</option>
          </select>
        </label>

        <label>
          Time projection
          <select
            value={projectionYears}
            onChange={(event) => handleProjectionYearsChange(event.target.value)}
            disabled={saving}
          >
            {Array.from({ length: 6 }, (_, offset) => 5 + offset).map((yearCount) => (
              <option key={yearCount} value={yearCount}>
                {yearCount} years
              </option>
            ))}
          </select>
        </label>

        <label>
          Reference real start date
          <RoadmapDateInput
            value={pendingRealStartDate}
            onChange={setPendingRealStartDate}
            ariaLabel="Reference real start date"
          />
        </label>

        {message ? (
          <div className={`settings-view__message settings-view__message--${messageType}`}>{message}</div>
        ) : null}
      </div>

      <DevelopmentPhasesPanel calendarMode={calendarMode} />

      <div className="settings-view__card">
        <div className="settings-view__section-heading">
          <h4>Payroll levels</h4>
          <p>The grade table (C1, C2, ... F4) positions can be assigned to in the Payroll Matrix.</p>
        </div>
        <button type="button" className="settings-view__btn" onClick={() => setPayrollLevelsModalOpen(true)}>
          Edit payroll settings
        </button>
      </div>

      <ProductSourcesCard />

      <MarketOpportunitySettingsCard />

      <div className="settings-view__card">
        <button
          type="button"
          className="settings-view__card-toggle"
          onClick={() => setIsExpensesCardExpanded((prev) => !prev)}
          aria-expanded={isExpensesCardExpanded}
        >
          <span className={`settings-view__tax-chevron ${isExpensesCardExpanded ? 'is-expanded' : ''}`}>▸</span>
          <div className="settings-view__section-heading">
            <h4>Expenses settings</h4>
            <p>Rename expense categories and choose which companies each one applies to. All companies are checked by default.</p>
          </div>
        </button>

        {isExpensesCardExpanded && (
          <>
            <div className="settings-view__expense-toolbar">
              {isAddingExpenseCategory ? (
                <div className="settings-view__expense-add-form">
                  <input
                    type="text"
                    value={newExpenseCategoryName}
                    onChange={(event) => setNewExpenseCategoryName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') handleSaveNewExpenseCategory()
                      if (event.key === 'Escape') handleCancelNewExpenseCategory()
                    }}
                    placeholder="Expense name"
                    autoFocus
                  />
                  <button type="button" className="settings-view__btn" onClick={handleSaveNewExpenseCategory}>
                    Save
                  </button>
                  <button type="button" className="settings-view__btn" onClick={handleCancelNewExpenseCategory}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button type="button" className="settings-view__btn" onClick={handleAddExpenseCategoryClick}>
                  + Add expense
                </button>
              )}
            </div>

            {expenseCategoriesStatus === 'loading' ? (
              <div className="settings-view__status">Loading expense categories...</div>
            ) : expenseRows.length === 0 ? (
              <div className="settings-view__status">No expense categories found.</div>
            ) : companies.length === 0 ? (
              <div className="settings-view__status">No companies in the corporate structure yet.</div>
            ) : (
              <div className="settings-view__expense-table-wrap">
                <table className="settings-view__expense-table">
                  <thead>
                    <tr>
                      <th className="settings-view__expense-name-col">Expense</th>
                      <th className="settings-view__expense-percent-col">% of</th>
                      {companies.map((company) => (
                        <th key={company.id}>{company.name}</th>
                      ))}
                      <th className="settings-view__expense-action-col" aria-hidden="true" />
                    </tr>
                  </thead>
                  <tbody>
                    {expenseRows.map((row) => {
                      const isProtected = PROTECTED_EXPENSE_CATEGORY_NAMES.has(row.name)
                      const draft = expenseNameDrafts[row.id] ?? row.name
                      const percentDraft = percentDraftFor(row)
                      const percentMetricLabel = PERCENT_OF_METRICS.find((item) => item.key === percentDraft.metric)?.label
                      const nameTitle = percentDraft.enabled
                        ? `Computed automatically — a percentage of ${percentMetricLabel} for each company below, instead of a fixed amount.`
                        : undefined
                      return (
                        <tr key={row.id}>
                          <td className="settings-view__expense-name-col" title={nameTitle}>
                            {isProtected ? (
                              <span
                                className="settings-view__expense-name-locked"
                                title="Computed automatically from Payroll — cannot be renamed."
                              >
                                {row.name}
                              </span>
                            ) : (
                              <input
                                type="text"
                                value={draft}
                                onChange={(event) => handleExpenseNameDraftChange(row.id, event.target.value)}
                                onBlur={() => handleExpenseNameBlur(row)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter') event.target.blur()
                                }}
                              />
                            )}
                          </td>
                          <td className="settings-view__expense-percent-col">
                            {isProtected ? null : (
                              <label className="settings-view__expense-percent-toggle">
                                <input
                                  type="checkbox"
                                  checked={percentDraft.enabled}
                                  onChange={(event) => handleTogglePercentOf(row, event.target.checked)}
                                  aria-label={`${row.name} is a percentage of a metric, instead of a fixed amount`}
                                />
                                {percentDraft.enabled && (
                                  <select
                                    value={percentDraft.metric}
                                    onChange={(event) => handleChangePercentMetric(row, event.target.value)}
                                    aria-label={`${row.name} percentage base`}
                                  >
                                    {PERCENT_OF_METRICS.map((metric) => (
                                      <option key={metric.key} value={metric.key}>
                                        {metric.label}
                                      </option>
                                    ))}
                                  </select>
                                )}
                              </label>
                            )}
                          </td>
                          {companies.map((company) => {
                            const setting = companySettingDraftFor(row.id, company.id)
                            const checked = !setting.excluded
                            return (
                              <td key={company.id} className="settings-view__expense-check-col">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => handleToggleExpenseApplicability(row.id, company.id, checked)}
                                  aria-label={`${row.name} applies to ${company.name}`}
                                />
                                {percentDraft.enabled && checked && (
                                  <span className="settings-view__expense-percent-input">
                                    <input
                                      type="number"
                                      min="0"
                                      step="0.1"
                                      value={setting.percentValue ?? ''}
                                      onChange={(event) => handleChangeCompanyPercentValue(row.id, company.id, event.target.value)}
                                      aria-label={`${row.name} percentage for ${company.name}`}
                                    />
                                    %
                                  </span>
                                )}
                              </td>
                            )
                          })}
                          <td className="settings-view__expense-action-col">
                            <button
                              type="button"
                              className="settings-view__expense-delete"
                              onClick={() => handleDeleteExpenseRow(row)}
                              aria-label={`Delete ${row.name}`}
                              title="Delete expense"
                            >
                              <IconX size={14} stroke={2} />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div className="settings-view__expense-save-row">
              <button
                type="button"
                className="settings-view__btn"
                onClick={handleSaveExpenseChanges}
                disabled={!expenseSettingsDirty || expenseSettingsSaving}
              >
                {expenseSettingsSaving ? 'Saving…' : 'Save changes'}
              </button>
              {expenseSettingsDirty && !expenseSettingsSaving && (
                <span className="settings-view__status-hint">You have unsaved changes.</span>
              )}
            </div>

            {expenseSettingsMessage ? (
              <div className={`settings-view__message settings-view__message--${expenseSettingsMessageType}`}>
                {expenseSettingsMessage}
              </div>
            ) : null}
          </>
        )}
      </div>

      <div className="settings-view__card">
        <button
          type="button"
          className="settings-view__card-toggle"
          onClick={() => setIsTaxStructureCardExpanded((prev) => !prev)}
          aria-expanded={isTaxStructureCardExpanded}
        >
          <span className={`settings-view__tax-chevron ${isTaxStructureCardExpanded ? 'is-expanded' : ''}`}>▸</span>
          <div className="settings-view__section-heading">
            <h4>Tax structure</h4>
            <p>One entry per country in the commercial structure — the categories below aren't wired up yet.</p>
          </div>
        </button>

        {isTaxStructureCardExpanded && (taxCountriesStatus === 'loading' ? (
          <div className="settings-view__status">Loading countries...</div>
        ) : taxCountries.length === 0 ? (
          <div className="settings-view__status">
            No countries in the commercial structure yet — add one under Operations → Commercial Structure first.
          </div>
        ) : (
          <div className="settings-view__tax-list">
            {taxCountries.map((country) => {
              const isExpanded = expandedTaxCountryIds.has(country.id)
              return (
                <div key={country.id} className="settings-view__tax-country">
                  <button
                    type="button"
                    className="settings-view__tax-country-toggle"
                    onClick={() => toggleTaxCountry(country.id)}
                    aria-expanded={isExpanded}
                  >
                    <span className={`settings-view__tax-chevron ${isExpanded ? 'is-expanded' : ''}`}>▸</span>
                    <span className="settings-view__tax-country-name">{country.name}</span>
                    {companies.length > 1 && <span className="settings-view__tax-company-tag">{country.companyName}</span>}
                  </button>
                  {isExpanded && (
                    <div className="settings-view__tax-pills">
                      {TAX_CATEGORIES.map((label) => {
                        const PanelComponent = WIRED_PILLS_BY_COUNTRY[country.name]?.[label]
                        if (!PanelComponent) {
                          return (
                            <span key={label} className="settings-view__tax-pill">
                              {label}
                            </span>
                          )
                        }
                        const pillKey = `${country.id}::${label}`
                        const isPillExpanded = expandedTaxPillKeys.has(pillKey)
                        return (
                          <div key={label} className="settings-view__tax-pill-wrap">
                            <button
                              type="button"
                              className={`settings-view__tax-pill settings-view__tax-pill--wired ${isPillExpanded ? 'is-expanded' : ''}`}
                              onClick={() => toggleTaxPill(pillKey)}
                              aria-expanded={isPillExpanded}
                            >
                              <span className={`settings-view__tax-pill-chevron ${isPillExpanded ? 'is-expanded' : ''}`}>▸</span>
                              {label}
                            </button>
                            {isPillExpanded && (
                              <div className="settings-view__tax-pill-panel">
                                <PanelComponent
                                  enabledBenefitKeys={enabledBenefitKeys}
                                  onToggleBenefit={handleToggleBenefit}
                                  calendarMode={calendarMode}
                                  countryCode={country.country_code}
                                  companyId={country.companyId}
                                />
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>

      <div className="settings-view__card">
        <div className="settings-view__section-heading">
          <h4>Delete company</h4>
          <p>Select a company card, then delete it.</p>
        </div>

        {companies.length === 0 ? (
          <div className="settings-view__status">No companies available.</div>
        ) : (
          <>
            <div className="settings-view__company-grid">
              {companies.map((company) => {
                const isSelected = company.id === selectedCompanyId
                const initials = company.name
                  .split(' ')
                  .slice(0, 2)
                  .map((part) => part[0])
                  .join('')
                  .toUpperCase()

                return (
                  <button
                    key={company.id}
                    type="button"
                    className={`settings-view__company-card ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedCompanyId(company.id)}
                  >
                    <span
                      className="settings-view__company-logo"
                      style={
                        company.logo
                          ? {
                              backgroundImage: `url(${company.logo})`,
                              backgroundSize: 'contain',
                              backgroundPosition: 'center',
                              backgroundRepeat: 'no-repeat',
                              backgroundColor: 'var(--bg-card)',
                            }
                          : {
                              background: `linear-gradient(135deg, ${company.accentFrom}, ${company.accentTo})`,
                            }
                      }
                    >
                      {!company.logo && initials}
                    </span>
                    <span className="settings-view__company-name">{company.name}</span>
                  </button>
                )
              })}
            </div>

            <div className="settings-view__delete-panel">
              {selectedCompany ? (
                <>
                  <div className="settings-view__selected-company">
                    <strong>{selectedCompany.name}</strong>
                    <span>{selectedCompany.companyType}</span>
                  </div>
                  <button
                    type="button"
                    className="settings-view__delete-btn"
                    onClick={async () => {
                      if (!window.confirm(`Delete ${selectedCompany.name}? This removes all related data.`)) return
                      try {
                        await deleteCompany(selectedCompany.id)
                        removeCompany(selectedCompany.id)
                        setSelectedCompanyId('')
                        setMessage(`${selectedCompany.name} was deleted.`)
                        setMessageType('info')
                        navigate('/settings')
                      } catch (error) {
                        setMessage(error.message || 'Failed to delete company. It has not been removed — please try again.')
                        setMessageType('error')
                      }
                    }}
                  >
                    Delete selected company
                  </button>
                </>
              ) : (
                <div className="settings-view__status">Select a company to delete.</div>
              )}
            </div>
          </>
        )}
      </div>

      {isPayrollLevelsModalOpen && <PayrollLevelsModal onClose={() => setPayrollLevelsModalOpen(false)} />}
    </section>
  )
}

export default SettingsView