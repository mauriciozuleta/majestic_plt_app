import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import { buildCountryProfile, fetchCountryProfile } from '../../../../services/commercialStructure'
import { runBackgroundJob } from '../../../../services/backgroundJobs'
import { exportCountryProfileToPdf } from './countryProfileExport'
import './CountryCommercialProfile.css'

// Renders the same fixed markdown shape the research prompt asks Claude to
// write (headings, paragraphs, list items) — not a general-purpose
// Markdown renderer.
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
    if (!line) {
      flush()
      return
    }
    if (line.startsWith('# ')) {
      flush()
      elements.push(<h1 key={key++}>{line.slice(2)}</h1>)
    } else if (line.startsWith('## ')) {
      flush()
      elements.push(<h2 key={key++}>{line.slice(3)}</h2>)
    } else if (line.startsWith('> ')) {
      flush()
      elements.push(<blockquote key={key++}>{line.slice(2)}</blockquote>)
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

// A rough "does this look like good/bad/neutral news" read on a Quick
// Facts value, purely to color the tile — not a real sentiment analysis.
function tileTone(value) {
  const v = value.toLowerCase()
  if (v.startsWith('yes')) return 'is-positive'
  if (v.startsWith('no') || v.startsWith('not found')) return 'is-neutral'
  return 'is-info'
}

function QuickFactsDashboard({ quickFacts }) {
  if (!quickFacts.length) return null
  return (
    <div className="country-profile-dashboard">
      {quickFacts.map((fact) => (
        <div key={fact.label} className={`country-profile-dashboard__tile ${tileTone(fact.value)}`}>
          <div className="country-profile-dashboard__label">{fact.label}</div>
          <div className="country-profile-dashboard__value">{fact.value}</div>
        </div>
      ))}
    </div>
  )
}

function CountryCommercialProfile({ companyId, country }) {
  const params = useParams()
  const resolvedCompanyId = companyId ?? params.companyId
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === resolvedCompanyId) ?? null
  const currentUser = useAppStore((state) => state.currentUser)

  const [state, setState] = useState({ status: 'idle', content: null, generatedAt: null, quickFacts: [], error: null })
  const [showViewer, setShowViewer] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)

  useEffect(() => {
    if (!country?.id) {
      setState({ status: 'idle', content: null, generatedAt: null, quickFacts: [], error: null })
      return undefined
    }
    let cancelled = false
    setState({ status: 'checking', content: null, generatedAt: null, quickFacts: [], error: null })
    fetchCountryProfile(resolvedCompanyId, country.id)
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
      .catch((error) => {
        if (cancelled) return
        setState({ status: 'error', content: null, generatedAt: null, quickFacts: [], error: error.message })
      })
    return () => {
      cancelled = true
    }
  }, [resolvedCompanyId, country?.id])

  const handleBuild = () => {
    if (!country?.id || state.status === 'building') return
    setState((prev) => ({ ...prev, status: 'building', error: null }))
    // Not awaited into this render's lifecycle on purpose — the poll loop
    // inside runBackgroundJob keeps going, and posts to the Assistant panel,
    // even if this component unmounts before it resolves (switching pills,
    // countries, or tabs). If it's still mounted when done, this .then also
    // updates the panel in place so the user doesn't have to reopen it.
    runBackgroundJob({
      start: () => buildCountryProfile(resolvedCompanyId, country.id),
      poll: () => fetchCountryProfile(resolvedCompanyId, country.id),
      label: `${country.name} Commercial Profile`,
    })
      .then((data) => {
        setState({ status: 'ready', content: data.content, generatedAt: data.generated_at, quickFacts: data.quick_facts ?? [], error: null })
      })
      .catch((error) => {
        setState((prev) => ({ ...prev, status: prev.content ? 'ready' : 'error', error: error.message }))
      })
  }

  const handleExportPdf = async () => {
    if (!state.content || exportingPdf) return
    setExportingPdf(true)
    try {
      await exportCountryProfileToPdf(
        state.content,
        { company, title: `${country?.name ?? 'Country'} — Commercial Profile`, exportedBy: currentUser?.name },
        `${(country?.name ?? 'country').toLowerCase().replace(/[^a-z0-9]+/g, '-')}-commercial-profile.pdf`,
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingPdf(false)
    }
  }

  if (!country) return null

  const hasProfile = state.status === 'ready'
  const isBusy = state.status === 'building' || state.status === 'checking'

  return (
    <div className="country-profile">
      <div className="country-profile__toolbar">
        {!hasProfile && (
          <button type="button" className="country-profile__btn" onClick={handleBuild} disabled={isBusy}>
            {state.status === 'building' ? 'Researching…' : state.status === 'checking' ? 'Loading…' : 'Build Profile'}
          </button>
        )}
        {hasProfile && (
          <>
            <button type="button" className="country-profile__btn" onClick={() => setShowViewer(true)}>
              View Full Profile
            </button>
            <button type="button" className="country-profile__btn country-profile__btn--secondary" onClick={handleBuild} disabled={isBusy}>
              {state.status === 'building' ? 'Updating…' : 'Update Profile'}
            </button>
          </>
        )}
      </div>
      {state.status === 'building' && (
        <span className="country-profile__hint">
          Live web research in progress — this can take a couple of minutes. It'll keep running even if you leave this tab; the Assistant
          panel will let you know when it's ready.
        </span>
      )}
      {state.status === 'error' && <span className="country-profile__error">{state.error}</span>}

      {hasProfile && (
        <>
          {state.generatedAt && (
            <span className="country-profile__meta">
              Last updated {new Date(state.generatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
          )}
          <QuickFactsDashboard quickFacts={state.quickFacts} />
        </>
      )}

      {showViewer && state.content && (
        <div className="country-profile-view__overlay">
          <div className="country-profile-view">
            <header className="country-profile-view__header">
              <div>
                <h3>{country.name} — Commercial Profile</h3>
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
                <button type="button" onClick={handleBuild} disabled={state.status === 'building'}>
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
    </div>
  )
}

export default CountryCommercialProfile
