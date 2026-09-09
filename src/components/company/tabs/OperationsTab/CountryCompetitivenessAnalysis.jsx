import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import {
  buildCompetitivenessAnalysis,
  fetchAllCompetitivenessAnalyses,
  fetchCompetitivenessAnalysis,
  fetchProfiledCountries,
} from '../../../../services/commercialStructure'
import { runBackgroundJob } from '../../../../services/backgroundJobs'
import { fetchPriceComparisonSnapshot } from './MarketAnalysis/priceComparisonFetchers'
import { mergeSources } from './MarketAnalysis/priceComparisonData'
import { fetchUsaSourcingSnapshot } from './MarketAnalysis/usaSourcingFetchers'
import { exportCountryProfileToPdf } from './countryProfileExport'
import './CountryCommercialProfile.css'

// Same fixed markdown shape as the Country Commercial Profile viewer.
function MarkdownBody({ markdown }) {
  const lines = markdown.split('\n')
  const elements = []
  let paragraph = []
  let key = 0
  const flush = () => {
    if (paragraph.length) {
      elements.push(<p key={key++}>{paragraph.join(' ')}</p>)
      paragraph = []
    }
  }
  lines.forEach((rawLine) => {
    const line = rawLine.trim()
    if (!line) return flush()
    if (line.startsWith('# ')) {
      flush()
      elements.push(<h1 key={key++}>{line.slice(2)}</h1>)
    } else if (line.startsWith('## ')) {
      flush()
      elements.push(<h2 key={key++}>{line.slice(3)}</h2>)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      flush()
      elements.push(<li key={key++}>{line.slice(2)}</li>)
    } else {
      paragraph.push(line)
    }
  })
  flush()
  return <div className="country-profile-view__body">{elements}</div>
}

function tileTone(value) {
  const v = value.toLowerCase()
  if (v.startsWith('high') || v.startsWith('none found')) return 'is-positive'
  if (v.startsWith('low')) return 'is-neutral'
  return 'is-info'
}

// Builds the {category, avg_price, unit, product_count, sample_products}
// summary the backend prompt needs — computed here, not on the backend,
// since each source's product shape differs (Colombia's is a two-source
// merge, USA's is a flat per-report list) and the frontend already knows
// how to read both correctly (see ColombiaProductAnalysisView/
// USASourcingView).
async function buildColombiaCategorySummary() {
  const snapshots = await fetchPriceComparisonSnapshot()
  const bySource = Object.fromEntries(snapshots.map((s) => [s.source, s.products]))
  const merged = mergeSources(bySource.la_mayorista || [], bySource.corabastos || [])
  return summarizeByCategory(
    merged.map((p) => ({
      category: p.category,
      price: p.laMayorista ?? p.corabastos,
      unit: 'COP',
      name: p.nameEs,
    })),
  )
}

async function buildUsaCategorySummary() {
  const snapshots = await fetchUsaSourcingSnapshot()
  const products = snapshots.flatMap((s) => s.products)
  return summarizeByCategory(products.map((p) => ({ category: p.category, price: p.price, unit: p.unit, name: p.product_en })))
}

function summarizeByCategory(rows) {
  const byCategory = new Map()
  rows.forEach((row) => {
    if (row.price == null || !row.category) return
    if (!byCategory.has(row.category)) byCategory.set(row.category, { prices: [], names: [], unit: row.unit })
    const bucket = byCategory.get(row.category)
    bucket.prices.push(row.price)
    bucket.names.push(row.name)
  })
  return Array.from(byCategory.entries()).map(([category, bucket]) => ({
    category,
    avg_price: Math.round((bucket.prices.reduce((sum, v) => sum + v, 0) / bucket.prices.length) * 100) / 100,
    unit: bucket.unit,
    product_count: bucket.prices.length,
    sample_products: Array.from(new Set(bucket.names)).slice(0, 5),
  }))
}

async function getCategorySummary(countryName) {
  const name = countryName.trim().toLowerCase()
  if (name === 'colombia') return buildColombiaCategorySummary()
  if (name === 'united states') return buildUsaCategorySummary()
  return null
}

function CountryCompetitivenessAnalysis({ companyId, sourceCountry }) {
  const params = useParams()
  const resolvedCompanyId = companyId ?? params.companyId
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === resolvedCompanyId) ?? null
  const currentUser = useAppStore((state) => state.currentUser)

  const [candidates, setCandidates] = useState([])
  const [candidatesStatus, setCandidatesStatus] = useState('loading')
  const [selectedTargetId, setSelectedTargetId] = useState('')
  const [state, setState] = useState({ status: 'idle', content: null, generatedAt: null, quickFacts: [], error: null })
  const [showViewer, setShowViewer] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)

  // Every analysis already built anywhere in the company that involves
  // this country — as either the source being benchmarked or the target
  // it was benchmarked against — so a country shows up here even if
  // someone else's tab is what actually ran the analysis.
  const [existingAnalyses, setExistingAnalyses] = useState([])
  const [existingStatus, setExistingStatus] = useState('loading')
  const [viewingExisting, setViewingExisting] = useState(null)
  const [exportingExistingKey, setExportingExistingKey] = useState(null)

  useEffect(() => {
    if (!sourceCountry?.id) return undefined
    let cancelled = false
    setCandidatesStatus('loading')
    fetchProfiledCountries(resolvedCompanyId)
      .then((rows) => {
        if (cancelled) return
        setCandidates(rows.filter((row) => row.country_id !== sourceCountry.id))
        setCandidatesStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setCandidatesStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [resolvedCompanyId, sourceCountry?.id])

  useEffect(() => {
    if (!sourceCountry?.name) return undefined
    let cancelled = false
    setExistingStatus('loading')
    const normalizedName = sourceCountry.name.trim().toLowerCase()
    fetchAllCompetitivenessAnalyses(resolvedCompanyId)
      .then((rows) => {
        if (cancelled) return
        setExistingAnalyses(
          rows.filter(
            (row) =>
              row.source_country_name?.trim().toLowerCase() === normalizedName ||
              row.target_country_name?.trim().toLowerCase() === normalizedName,
          ),
        )
        setExistingStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setExistingStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [resolvedCompanyId, sourceCountry?.name])

  const existingRowKey = (row) => `${row.target_country_id}__${row.source_country_name}`

  const handleViewExisting = async (row) => {
    const data = await fetchCompetitivenessAnalysis(resolvedCompanyId, row.target_country_id, row.source_country_name)
    if (data.exists) {
      setViewingExisting({ title: `${row.source_country_name} → ${row.target_country_name} — Competitiveness`, content: data.content })
    }
  }

  const handleExportExistingPdf = async (row) => {
    setExportingExistingKey(existingRowKey(row))
    try {
      const data = await fetchCompetitivenessAnalysis(resolvedCompanyId, row.target_country_id, row.source_country_name)
      if (!data.exists) return
      await exportCountryProfileToPdf(
        data.content,
        {
          company,
          title: `${row.source_country_name} → ${row.target_country_name} — Competitiveness Analysis`,
          exportedBy: currentUser?.name,
        },
        `${row.source_country_name}-vs-${row.target_country_name}-competitiveness.pdf`.toLowerCase().replace(/[^a-z0-9.-]+/g, '-'),
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingExistingKey(null)
    }
  }

  useEffect(() => {
    if (!selectedTargetId) {
      setState({ status: 'idle', content: null, generatedAt: null, quickFacts: [], error: null })
      return undefined
    }
    let cancelled = false
    setState({ status: 'checking', content: null, generatedAt: null, quickFacts: [], error: null })
    fetchCompetitivenessAnalysis(resolvedCompanyId, selectedTargetId, sourceCountry.name)
      .then((data) => {
        if (cancelled) return
        if (data.exists) {
          setState({ status: 'ready', content: data.content, generatedAt: data.generated_at, quickFacts: data.quick_facts ?? [], error: null })
        } else if (data.building) {
          setState({ status: 'building', content: null, generatedAt: null, quickFacts: [], error: null })
        } else {
          setState({ status: 'none', content: null, generatedAt: null, quickFacts: [], error: data.error })
        }
      })
      .catch((error) => !cancelled && setState({ status: 'error', content: null, generatedAt: null, quickFacts: [], error: error.message }))
    return () => {
      cancelled = true
    }
  }, [resolvedCompanyId, selectedTargetId, sourceCountry?.name])

  const handleAnalyze = () => {
    if (!selectedTargetId || state.status === 'building') return
    setState((prev) => ({ ...prev, status: 'building', error: null }))

    // Captured now, not read live from state during the poll — if the user
    // changes the dropdown selection while this job is still running, this
    // job must keep tracking the pair it was actually started for.
    const targetId = selectedTargetId
    const targetName = candidates.find((c) => c.country_id === targetId)?.country_name ?? 'target country'
    const sourceName = sourceCountry.name

    runBackgroundJob({
      start: async () => {
        const categorySummary = await getCategorySummary(sourceName)
        if (!categorySummary || !categorySummary.length) {
          throw new Error(`No Product Analysis data loaded for ${sourceName} yet — click Update on its Product Analysis tab first.`)
        }
        return buildCompetitivenessAnalysis(resolvedCompanyId, targetId, sourceName, categorySummary)
      },
      poll: () => fetchCompetitivenessAnalysis(resolvedCompanyId, targetId, sourceName),
      label: `${sourceName} → ${targetName} Competitiveness Analysis`,
    })
      .then((data) => {
        setState({ status: 'ready', content: data.content, generatedAt: data.generated_at, quickFacts: data.quick_facts ?? [], error: null })
      })
      .catch((error) => {
        setState((prev) => ({ ...prev, status: prev.content ? 'ready' : 'error', error: error.message }))
      })
  }

  const targetCountry = candidates.find((c) => c.country_id === selectedTargetId)

  const handleExportPdf = async () => {
    if (!state.content || exportingPdf) return
    setExportingPdf(true)
    try {
      await exportCountryProfileToPdf(
        state.content,
        {
          company,
          title: `${sourceCountry.name} → ${targetCountry?.country_name ?? ''} — Competitiveness Analysis`,
          exportedBy: currentUser?.name,
        },
        `${sourceCountry.name.toLowerCase()}-vs-${(targetCountry?.country_name ?? 'target').toLowerCase()}-competitiveness.pdf`.replace(
          /[^a-z0-9.-]+/g,
          '-',
        ),
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingPdf(false)
    }
  }

  if (!sourceCountry) return null

  const hasAnalysis = state.status === 'ready'
  const isBusy = state.status === 'building' || state.status === 'checking'

  return (
    <div className="country-profile">
      {existingStatus === 'ready' && existingAnalyses.length > 0 && (
        <div className="country-profile__existing">
          <span className="country-profile__existing-heading">Already built involving {sourceCountry.name}</span>
          {existingAnalyses.map((row) => (
            <div key={existingRowKey(row)} className="country-profile__existing-row">
              <span className="country-profile__existing-name">
                {row.source_country_name} → {row.target_country_name} — Competitiveness
              </span>
              <div className="country-profile__existing-actions">
                <button type="button" className="country-profile__btn country-profile__btn--secondary" onClick={() => handleViewExisting(row)}>
                  View
                </button>
                <button
                  type="button"
                  className="country-profile__btn country-profile__btn--secondary"
                  onClick={() => handleExportExistingPdf(row)}
                  disabled={exportingExistingKey === existingRowKey(row)}
                >
                  {exportingExistingKey === existingRowKey(row) ? 'Exporting…' : 'Export PDF'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <p style={{ margin: 0, color: '#8ea3c2', fontSize: '0.85rem' }}>
        Pick a country to benchmark {sourceCountry.name}'s Product Analysis portfolio against. Only countries with a Country Commercial
        Profile already built can be used — a benchmark needs that context.
      </p>

      {candidatesStatus === 'loading' && <p style={{ color: '#8ea3c2', margin: 0 }}>Loading countries…</p>}
      {candidatesStatus === 'error' && <p style={{ color: '#fca5a5', margin: 0 }}>Could not load the list of countries.</p>}
      {candidatesStatus === 'ready' && candidates.length === 0 && (
        <p style={{ color: '#8ea3c2', margin: 0 }}>
          No other country has a Country Commercial Profile yet. Build one first (in that country's own tab) before you can benchmark
          against it.
        </p>
      )}

      {candidatesStatus === 'ready' && candidates.length > 0 && (
        <div className="country-profile__toolbar">
          <select
            value={selectedTargetId}
            onChange={(event) => setSelectedTargetId(event.target.value)}
            style={{
              background: '#111f31',
              color: '#eaf3ff',
              border: '1px solid #3b82f6',
              borderRadius: '8px',
              padding: '8px 12px',
              fontSize: '0.85rem',
            }}
          >
            <option value="">-- Select a country to benchmark against --</option>
            {candidates.map((c) => (
              <option key={c.country_id} value={c.country_id}>
                {c.country_name}
              </option>
            ))}
          </select>

          {selectedTargetId && !hasAnalysis && (
            <button type="button" className="country-profile__btn" onClick={handleAnalyze} disabled={isBusy}>
              {state.status === 'building' ? 'Analyzing…' : state.status === 'checking' ? 'Loading…' : 'Analyze Competitiveness'}
            </button>
          )}
          {selectedTargetId && hasAnalysis && (
            <>
              <button type="button" className="country-profile__btn" onClick={() => setShowViewer(true)}>
                View Full Analysis
              </button>
              <button type="button" className="country-profile__btn country-profile__btn--secondary" onClick={handleAnalyze} disabled={isBusy}>
                {state.status === 'building' ? 'Updating…' : 'Update Analysis'}
              </button>
            </>
          )}
        </div>
      )}

      {state.status === 'building' && (
        <span className="country-profile__hint">
          Live analysis in progress — this can take a couple of minutes. It'll keep running even if you leave this tab; the Assistant panel
          will let you know when it's ready.
        </span>
      )}
      {state.status === 'error' && <span className="country-profile__error">{state.error}</span>}

      {hasAnalysis && (
        <>
          {state.generatedAt && (
            <span className="country-profile__meta">
              Last updated {new Date(state.generatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
          )}
          {state.quickFacts.length > 0 && (
            <div className="country-profile-dashboard">
              {state.quickFacts.map((fact) => (
                <div key={fact.label} className={`country-profile-dashboard__tile ${tileTone(fact.value)}`}>
                  <div className="country-profile-dashboard__label">{fact.label}</div>
                  <div className="country-profile-dashboard__value">{fact.value}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {showViewer && state.content && (
        <div className="country-profile-view__overlay">
          <div className="country-profile-view">
            <header className="country-profile-view__header">
              <div>
                <h3>
                  {sourceCountry.name} → {targetCountry?.country_name} — Competitiveness
                </h3>
                {state.generatedAt && (
                  <span className="country-profile-view__meta">
                    Generated {new Date(state.generatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                  </span>
                )}
              </div>
              <div className="country-profile-view__actions">
                <button type="button" onClick={handleExportPdf} disabled={exportingPdf}>
                  {exportingPdf ? 'Exporting…' : 'Export PDF'}
                </button>
                <button type="button" onClick={handleAnalyze} disabled={state.status === 'building'}>
                  Update
                </button>
                <button type="button" className="country-profile-view__close" onClick={() => setShowViewer(false)}>
                  Close
                </button>
              </div>
            </header>
            <div className="country-profile-view__scroll">
              <MarkdownBody markdown={state.content} />
            </div>
          </div>
        </div>
      )}

      {viewingExisting && (
        <div className="country-profile-view__overlay">
          <div className="country-profile-view">
            <header className="country-profile-view__header">
              <h3>{viewingExisting.title}</h3>
              <div className="country-profile-view__actions">
                <button type="button" className="country-profile-view__close" onClick={() => setViewingExisting(null)}>
                  Close
                </button>
              </div>
            </header>
            <div className="country-profile-view__scroll">
              <MarkdownBody markdown={viewingExisting.content} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CountryCompetitivenessAnalysis
