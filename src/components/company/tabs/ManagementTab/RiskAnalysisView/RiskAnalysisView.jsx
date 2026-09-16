import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createMechanism,
  createRisk,
  createRiskCategory,
  deleteMechanism,
  deleteRisk,
  deleteRiskCategory,
  fetchRiskAnalysis,
  updateMechanism,
  updateRisk,
  updateRiskCategory,
} from '../../../../../services/riskAnalysis'
import { LEVELS, LEVEL_LABEL, TIER_COLOR, TIER_LABEL, WELL_MANAGED_THRESHOLD } from '../../../../../utils/riskScoring'
import HelpPopover from './HelpPopover'
import RiskEntryModal from './RiskEntryModal'
import GeneratePlanModal from './GeneratePlanModal'
import './RiskAnalysisView.css'

function scoreColor(value, direction) {
  const t = (value - 1) / 4
  const good = direction === 'up' ? t : 1 - t
  if (good >= 0.66) return { fg: '#eafff5', bg: 'rgba(53,211,153,0.16)', border: 'rgba(53,211,153,0.5)' }
  if (good >= 0.33) return { fg: '#F2C77D', bg: 'rgba(232,163,61,0.16)', border: 'rgba(232,163,61,0.5)' }
  return { fg: '#FCA5A5', bg: 'rgba(248,113,113,0.14)', border: 'rgba(248,113,113,0.45)' }
}

function ScorePill({ value, direction }) {
  const c = scoreColor(value, direction)
  return (
    <span className="score-pill" style={{ color: c.fg, background: c.bg, border: `1px solid ${c.border}` }}>
      {value.toFixed(1)}
    </span>
  )
}

function LevelSelect({ value, onChange }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {LEVELS.map((lv) => (
        <option key={lv} value={lv}>
          {lv} · {LEVEL_LABEL[lv]}
        </option>
      ))}
    </select>
  )
}

function ComparisonBar({ risk }) {
  const hasMechanisms = risk.mechanisms.length > 0
  const net = hasMechanisms ? risk.net_score : 0
  const magnitude = (Math.min(Math.abs(net), 4) / 4) * 50
  const tier = risk.management_tier
  const verdict = !hasMechanisms
    ? { text: 'No mechanisms yet', color: 'var(--text-dim)' }
    : { text: `${TIER_LABEL[tier]} (${net >= 0 ? '+' : ''}${net.toFixed(1)})`, color: TIER_COLOR[tier] }
  const fill = !hasMechanisms
    ? null
    : net >= 0
      ? { left: '50%', width: `${magnitude}%`, background: 'linear-gradient(90deg, rgba(53,211,153,0.25), #35D399)' }
      : { right: '50%', width: `${magnitude}%`, background: 'linear-gradient(270deg, rgba(248,113,113,0.25), #F87171)' }

  return (
    <div className="comparison-bar">
      <div
        className="comparison-track"
        title={`Exposure ${risk.exposure_score.toFixed(1)} vs Mitigation ${hasMechanisms ? risk.mitigation_score.toFixed(1) : '—'}`}
      >
        {fill && <div className="comparison-fill" style={fill} />}
        <div className="comparison-center-tick" />
      </div>
      <div className="comparison-verdict" style={{ color: verdict.color }}>
        {verdict.text}
      </div>
    </div>
  )
}

function ExposureHelp() {
  return (
    <>
      <p>
        <b>Exposure</b> = average(Probability, Impact) — how likely this risk is, and how bad it would be. Lower is
        safer.
      </p>
      <p>
        <b>Mitigation</b> = average(Capacity, Cost) across every mechanism for that risk — Capacity is how well the
        mechanism actually works, Cost is inverted (a cheap mechanism scores higher, not lower).
      </p>
      <p>
        <b>Net</b> = Mitigation − Exposure. A risk is "Well managed" once Net reaches +{WELL_MANAGED_THRESHOLD} — only
        risks at that tier are eligible for Generate Plan.
      </p>
    </>
  )
}

function RiskAnalysisView() {
  const { companyId } = useParams()
  const [categories, setCategories] = useState([])
  const [activeCategoryId, setActiveCategoryId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [entryModal, setEntryModal] = useState(null) // { kind: 'risk'|'mechanism', categoryId, riskId }
  const [planModalOpen, setPlanModalOpen] = useState(false)

  const reload = async (keepActiveId) => {
    if (!companyId) return
    setError('')
    try {
      const data = await fetchRiskAnalysis(companyId)
      setCategories(data.categories)
      setActiveCategoryId((prev) => {
        const wanted = keepActiveId ?? prev
        return data.categories.some((c) => c.id === wanted) ? wanted : data.categories[0]?.id ?? null
      })
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

  const activeCategory = categories.find((c) => c.id === activeCategoryId) ?? null

  const handleAddCategory = async () => {
    const name = window.prompt('New category name')
    if (!name || !name.trim()) return
    const created = await createRiskCategory(companyId, name.trim())
    await reload(created.id)
  }

  const handleRenameCategory = async (category) => {
    const name = window.prompt('Rename category', category.name)
    if (!name || !name.trim() || name.trim() === category.name) return
    await updateRiskCategory(category.id, name.trim())
    await reload(category.id)
  }

  const handleDeleteCategory = async (category) => {
    if (!window.confirm(`Delete "${category.name}" and every risk in it? This can't be undone.`)) return
    await deleteRiskCategory(category.id)
    await reload()
  }

  const handleSaveRisk = async ({ name, description }) => {
    const created = await createRisk(entryModal.categoryId, { name, description })
    setEntryModal(null)
    await reload(entryModal.categoryId)
    return created
  }

  const handleSaveMechanism = async ({ name, description }) => {
    await createMechanism(entryModal.riskId, { name, description })
    setEntryModal(null)
    await reload(activeCategoryId)
  }

  const handleDeleteRisk = async (risk) => {
    if (!window.confirm(`Delete "${risk.name}"? This can't be undone.`)) return
    await deleteRisk(risk.id)
    await reload(activeCategoryId)
  }

  const handleDeleteMechanism = async (mechanism) => {
    if (!window.confirm(`Delete "${mechanism.name}"? This can't be undone.`)) return
    await deleteMechanism(mechanism.id)
    await reload(activeCategoryId)
  }

  const handleRiskNameBlur = async (risk, value) => {
    const trimmed = value.trim()
    if (!trimmed || trimmed === risk.name) return
    await updateRisk(risk.id, {
      name: trimmed,
      description: risk.description,
      probability: risk.probability,
      impact: risk.impact,
    })
    await reload(activeCategoryId)
  }

  const handleRiskLevelChange = async (risk, field, value) => {
    await updateRisk(risk.id, {
      name: risk.name,
      description: risk.description,
      probability: field === 'probability' ? value : risk.probability,
      impact: field === 'impact' ? value : risk.impact,
    })
    await reload(activeCategoryId)
  }

  const handleMechanismNameBlur = async (mechanism, value) => {
    const trimmed = value.trim()
    if (!trimmed || trimmed === mechanism.name) return
    await updateMechanism(mechanism.id, {
      name: trimmed,
      description: mechanism.description,
      capacity: mechanism.capacity,
      cost: mechanism.cost,
    })
    await reload(activeCategoryId)
  }

  const handleMechanismLevelChange = async (mechanism, field, value) => {
    await updateMechanism(mechanism.id, {
      name: mechanism.name,
      description: mechanism.description,
      capacity: field === 'capacity' ? value : mechanism.capacity,
      cost: field === 'cost' ? value : mechanism.cost,
    })
    await reload(activeCategoryId)
  }

  if (loading) return <div className="panel-surface risk-analysis__status">Loading risk analysis...</div>

  return (
    <div className="panel-surface risk-analysis">
      <div className="risk-analysis__header">
        <div className="risk-analysis__title-group">
          <h3>Risk Analysis &amp; Management</h3>
          <HelpPopover>
            <ExposureHelp />
          </HelpPopover>
        </div>
        <button type="button" className="btn" onClick={() => setPlanModalOpen(true)} disabled={categories.length === 0}>
          Generate Plan
        </button>
      </div>

      {error && <div className="risk-analysis__error">{error}</div>}

      <div className="tab-bar">
        {categories.map((cat) => (
          <button
            key={cat.id}
            type="button"
            className={`tab ${cat.id === activeCategoryId ? 'is-active' : ''}`}
            onClick={() => setActiveCategoryId(cat.id)}
          >
            <span className="tab-dot" style={{ background: cat.color }} />
            <span>{cat.name}</span>
          </button>
        ))}
        <button type="button" className="tab tab--add" onClick={handleAddCategory}>
          + Category
        </button>
      </div>

      {activeCategory && (
        <div className="category-panel">
          <div className="category-panel__header">
            <div className="category-panel__title">
              <span className="category-panel__bar" style={{ background: activeCategory.color }} />
              <h3>{activeCategory.name}</h3>
              {activeCategory.is_custom && (
                <>
                  <button type="button" className="btn btn--icon" title="Rename" onClick={() => handleRenameCategory(activeCategory)}>
                    ✎
                  </button>
                  <button
                    type="button"
                    className="btn btn--icon btn--danger-ghost"
                    title="Delete category"
                    onClick={() => handleDeleteCategory(activeCategory)}
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
            <button
              type="button"
              className="pill-btn pill-btn--risk"
              onClick={() => setEntryModal({ kind: 'risk', categoryId: activeCategory.id })}
            >
              + Add risk
            </button>
          </div>

          <div className="risk-list">
            {activeCategory.risks.length === 0 && (
              <div className="empty-note">No risks identified yet in this category — add one to get started.</div>
            )}
            {activeCategory.risks.map((risk) => (
              <RiskCard
                key={risk.id}
                risk={risk}
                onNameBlur={(value) => handleRiskNameBlur(risk, value)}
                onLevelChange={(field, value) => handleRiskLevelChange(risk, field, value)}
                onDelete={() => handleDeleteRisk(risk)}
                onAddMechanism={() => setEntryModal({ kind: 'mechanism', riskId: risk.id })}
                onMechanismNameBlur={(mechanism, value) => handleMechanismNameBlur(mechanism, value)}
                onMechanismLevelChange={(mechanism, field, value) => handleMechanismLevelChange(mechanism, field, value)}
                onDeleteMechanism={handleDeleteMechanism}
              />
            ))}
          </div>
        </div>
      )}

      {entryModal && (
        <RiskEntryModal
          kind={entryModal.kind}
          onCancel={() => setEntryModal(null)}
          onSave={entryModal.kind === 'risk' ? handleSaveRisk : handleSaveMechanism}
        />
      )}

      {planModalOpen && (
        <GeneratePlanModal companyId={companyId} categories={categories} onClose={() => setPlanModalOpen(false)} />
      )}
    </div>
  )
}

function RiskCard({ risk, onNameBlur, onLevelChange, onDelete, onAddMechanism, onMechanismNameBlur, onMechanismLevelChange, onDeleteMechanism }) {
  const [mechanismsOpen, setMechanismsOpen] = useState(true)
  const [nameDraft, setNameDraft] = useState(risk.name)

  useEffect(() => setNameDraft(risk.name), [risk.name])

  return (
    <div className="risk">
      <div className="risk__head">
        <div className="risk__title-block">
          <input
            className="risk__name"
            value={nameDraft}
            onChange={(event) => setNameDraft(event.target.value)}
            onBlur={(event) => onNameBlur(event.target.value)}
          />
          {risk.description && <div className="risk__danger">{risk.description}</div>}
        </div>
        <div className="risk__scoring">
          <label>
            Probability
            <LevelSelect value={risk.probability} onChange={(value) => onLevelChange('probability', value)} />
          </label>
          <label>
            Impact
            <LevelSelect value={risk.impact} onChange={(value) => onLevelChange('impact', value)} />
          </label>
        </div>
        <ScorePill value={risk.exposure_score} direction="down" />
        <button type="button" className="btn btn--icon btn--danger-ghost" title="Remove risk" onClick={onDelete}>
          ✕
        </button>
      </div>
      <div className="risk__body">
        <div className="mechanisms-label" onClick={() => setMechanismsOpen((prev) => !prev)}>
          <span className="mechanisms-label__left">
            <span className={`mechanisms-chevron ${mechanismsOpen ? 'is-open' : ''}`}>▸</span>
            <span>
              Management mechanisms <span className="mechanisms-count">({risk.mechanisms.length})</span>
            </span>
          </span>
          <button
            type="button"
            className="pill-btn pill-btn--mech"
            onClick={(event) => {
              event.stopPropagation()
              setMechanismsOpen(true)
              onAddMechanism()
            }}
          >
            + Add mechanism
          </button>
        </div>
        {mechanismsOpen &&
          (risk.mechanisms.length === 0 ? (
            <div className="empty-note">No mechanisms yet — add at least one.</div>
          ) : (
            risk.mechanisms.map((mechanism) => (
              <MechanismRow
                key={mechanism.id}
                mechanism={mechanism}
                onNameBlur={(value) => onMechanismNameBlur(mechanism, value)}
                onLevelChange={(field, value) => onMechanismLevelChange(mechanism, field, value)}
                onDelete={() => onDeleteMechanism(mechanism)}
              />
            ))
          ))}
        <ComparisonBar risk={risk} />
      </div>
    </div>
  )
}

function MechanismRow({ mechanism, onNameBlur, onLevelChange, onDelete }) {
  const [nameDraft, setNameDraft] = useState(mechanism.name)
  useEffect(() => setNameDraft(mechanism.name), [mechanism.name])

  return (
    <div className="mechanism-row">
      <div className="mechanism__title-block">
        <input
          type="text"
          value={nameDraft}
          onChange={(event) => setNameDraft(event.target.value)}
          onBlur={(event) => onNameBlur(event.target.value)}
        />
        {mechanism.description && <div className="mechanism__note">{mechanism.description}</div>}
      </div>
      <label className="mechanism-field">
        Capacity
        <LevelSelect value={mechanism.capacity} onChange={(value) => onLevelChange('capacity', value)} />
      </label>
      <label className="mechanism-field">
        Cost
        <LevelSelect value={mechanism.cost} onChange={(value) => onLevelChange('cost', value)} />
      </label>
      <ScorePill value={mechanism.score} direction="up" />
      <button type="button" className="btn btn--icon btn--danger-ghost" title="Remove mechanism" onClick={onDelete}>
        ✕
      </button>
    </div>
  )
}

export default RiskAnalysisView
