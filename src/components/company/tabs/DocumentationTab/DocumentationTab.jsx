import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../store/useAppStore'
import { fetchStartupInvestmentPlan, fetchStartupInvestmentRecords } from '../../../../services/startupInvestment'
import {
  fetchAllCompetitivenessAnalyses,
  fetchCommercialCountries,
  fetchCompetitivenessAnalysis,
  fetchCountryProfile,
  fetchProfiledCountries,
} from '../../../../services/commercialStructure'
import { downloadCsv } from '../../../../utils/exportCsv'
import { buildStartupInvestmentPdfSpec } from '../FinancialTab/startupInvestmentPdfSpec'
import { exportCountryProfileToPdf } from '../OperationsTab/countryProfileExport'
import { buildProductPortfolio } from '../../../../services/productPortfolio'
import ExportPdfButton from '../../../shared/PdfExport/ExportPdfButton'
import './DocumentationTab.css'

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
  return <div className="documentation__markdown-body">{elements}</div>
}

function StartupInvestmentCategory({ companyId }) {
  const [state, setState] = useState({ status: 'loading', plan: null, records: [] })

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchStartupInvestmentPlan(companyId), fetchStartupInvestmentRecords(companyId)])
      .then(([plan, records]) => {
        if (cancelled) return
        setState({ status: plan ? 'ready' : 'none', plan, records })
      })
      .catch(() => !cancelled && setState({ status: 'error', plan: null, records: [] }))
    return () => {
      cancelled = true
    }
  }, [companyId])

  if (state.status === 'loading') return <p className="documentation__hint">Loading…</p>
  if (state.status === 'error') return <p className="documentation__hint documentation__hint--error">Could not load this document.</p>
  if (state.status === 'none') return <p className="documentation__hint">No Start-up Investment plan has been created yet.</p>

  const spec = buildStartupInvestmentPdfSpec(state.plan, state.records)
  return (
    <div className="documentation__link-row">
      <span className="documentation__link-name">Start-up Investment Requirement</span>
      <ExportPdfButton spec={spec} companyId={companyId} label="View PDF" className="documentation__link-btn" />
    </div>
  )
}

function CountryProfilesCategory({ companyId }) {
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === companyId) ?? null
  const currentUser = useAppStore((state) => state.currentUser)

  const [countries, setCountries] = useState([])
  const [status, setStatus] = useState('loading')
  const [viewing, setViewing] = useState(null)
  const [exportingId, setExportingId] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchProfiledCountries(companyId)
      .then((rows) => {
        if (cancelled) return
        setCountries(rows)
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [companyId])

  const handleView = async (row) => {
    const data = await fetchCountryProfile(companyId, row.country_id)
    if (data.exists) setViewing({ countryName: row.country_name, content: data.content, generatedAt: data.generated_at })
  }

  const handleExportPdf = async (row) => {
    setExportingId(row.country_id)
    try {
      const data = await fetchCountryProfile(companyId, row.country_id)
      if (!data.exists) return
      await exportCountryProfileToPdf(
        data.content,
        { company, title: `${row.country_name} — Commercial Profile`, exportedBy: currentUser?.name },
        `${row.country_name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-commercial-profile.pdf`,
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingId(null)
    }
  }

  if (status === 'loading') return <p className="documentation__hint">Loading…</p>
  if (status === 'error') return <p className="documentation__hint documentation__hint--error">Could not load country profiles.</p>
  if (countries.length === 0) {
    return <p className="documentation__hint">No Country Commercial Profiles have been built yet (Operations → Market Analysis).</p>
  }

  return (
    <>
      {countries.map((row) => (
        <div key={row.country_id} className="documentation__link-row">
          <span className="documentation__link-name">{row.country_name} — Commercial Profile</span>
          <div className="documentation__link-actions">
            <button type="button" className="documentation__link-btn" onClick={() => handleView(row)}>
              View
            </button>
            <button
              type="button"
              className="documentation__link-btn"
              onClick={() => handleExportPdf(row)}
              disabled={exportingId === row.country_id}
            >
              {exportingId === row.country_id ? 'Exporting…' : 'Export PDF'}
            </button>
          </div>
        </div>
      ))}

      {viewing && (
        <div className="documentation__viewer-overlay">
          <div className="documentation__viewer">
            <header className="documentation__viewer-header">
              <h3>{viewing.countryName} — Commercial Profile</h3>
              <button type="button" className="documentation__link-btn" onClick={() => setViewing(null)}>
                Close
              </button>
            </header>
            <div className="documentation__viewer-scroll">
              <MarkdownBody markdown={viewing.content} />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function CompetitivenessAnalysesCategory({ companyId }) {
  const companies = useAppStore((state) => state.companies)
  const company = companies.find((item) => item.id === companyId) ?? null
  const currentUser = useAppStore((state) => state.currentUser)

  const [analyses, setAnalyses] = useState([])
  const [status, setStatus] = useState('loading')
  const [viewing, setViewing] = useState(null)
  const [exportingKey, setExportingKey] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchAllCompetitivenessAnalyses(companyId)
      .then((rows) => {
        if (cancelled) return
        setAnalyses(rows)
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [companyId])

  const rowKey = (row) => `${row.target_country_id}__${row.source_country_name}`

  const handleView = async (row) => {
    const data = await fetchCompetitivenessAnalysis(companyId, row.target_country_id, row.source_country_name)
    if (data.exists) {
      setViewing({
        title: `${row.source_country_name} → ${row.target_country_name} — Competitiveness`,
        content: data.content,
      })
    }
  }

  const handleExportPdf = async (row) => {
    setExportingKey(rowKey(row))
    try {
      const data = await fetchCompetitivenessAnalysis(companyId, row.target_country_id, row.source_country_name)
      if (!data.exists) return
      await exportCountryProfileToPdf(
        data.content,
        { company, title: `${row.source_country_name} → ${row.target_country_name} — Competitiveness Analysis`, exportedBy: currentUser?.name },
        `${row.source_country_name}-vs-${row.target_country_name}-competitiveness.pdf`.toLowerCase().replace(/[^a-z0-9.-]+/g, '-'),
      )
    } catch (error) {
      window.alert(`Could not generate the PDF: ${error.message}`)
    } finally {
      setExportingKey(null)
    }
  }

  if (status === 'loading') return <p className="documentation__hint">Loading…</p>
  if (status === 'error') return <p className="documentation__hint documentation__hint--error">Could not load competitiveness analyses.</p>
  if (analyses.length === 0) {
    return (
      <p className="documentation__hint">
        No Country Competitiveness Analyses have been run yet (Operations → Market Analysis → Country Competitiveness Analysis).
      </p>
    )
  }

  return (
    <>
      {analyses.map((row) => (
        <div key={rowKey(row)} className="documentation__link-row">
          <span className="documentation__link-name">
            {row.source_country_name} → {row.target_country_name} — Competitiveness
          </span>
          <div className="documentation__link-actions">
            <button type="button" className="documentation__link-btn" onClick={() => handleView(row)}>
              View
            </button>
            <button
              type="button"
              className="documentation__link-btn"
              onClick={() => handleExportPdf(row)}
              disabled={exportingKey === rowKey(row)}
            >
              {exportingKey === rowKey(row) ? 'Exporting…' : 'Export PDF'}
            </button>
          </div>
        </div>
      ))}

      {viewing && (
        <div className="documentation__viewer-overlay">
          <div className="documentation__viewer">
            <header className="documentation__viewer-header">
              <h3>{viewing.title}</h3>
              <button type="button" className="documentation__link-btn" onClick={() => setViewing(null)}>
                Close
              </button>
            </header>
            <div className="documentation__viewer-scroll">
              <MarkdownBody markdown={viewing.content} />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function ProductPortfolioCategory({ companyId }) {
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('loading')
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    fetchCommercialCountries(companyId)
      .then((countries) => {
        const countryCodeByName = new Map(countries.map((c) => [c.name.toLowerCase(), c.country_code]))
        return buildProductPortfolio(countryCodeByName)
      })
      .then((portfolio) => {
        if (cancelled) return
        setRows(portfolio)
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
    // Recomputed fresh every time this tab mounts — there's no separate
    // "product portfolio changed" event to listen for, so re-deriving from
    // the current snapshot data on each visit is what keeps this current.
  }, [companyId])

  const handleExportCsv = () => {
    downloadCsv(
      'general-portfolio-directory.csv',
      ['Code', 'Product', 'Category', 'Countries'],
      rows.map((row) => [row.code, row.name, row.category, row.countries.join(', ')]),
    )
  }

  if (status === 'loading') return <p className="documentation__hint">Loading…</p>
  if (status === 'error') return <p className="documentation__hint documentation__hint--error">Could not load the product portfolio.</p>
  if (rows.length === 0) {
    return (
      <p className="documentation__hint">
        No product portfolio data yet — click Update on a country's Product Analysis tab first (Operations → Market Analysis).
      </p>
    )
  }

  return (
    <>
      <div className="documentation__portfolio-toolbar">
        <div className="documentation__portfolio-toolbar-left">
          <button
            type="button"
            className="documentation__collapse-btn"
            onClick={() => setCollapsed((prev) => !prev)}
            title={collapsed ? 'Expand the product table' : 'Collapse the product table'}
          >
            {collapsed ? '▸' : '▾'}
          </button>
          <span className="documentation__hint">{rows.length} distinct products across all countries.</span>
        </div>
        <button type="button" className="documentation__link-btn" onClick={handleExportCsv}>
          Export CSV
        </button>
      </div>
      {!collapsed && (
        <div className="documentation__portfolio-table-wrap">
          <table className="documentation__portfolio-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Product</th>
                <th>Category</th>
                <th>Countries</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <td className="documentation__portfolio-code">{row.code}</td>
                  <td>{row.name}</td>
                  <td className="documentation__portfolio-muted">{row.category}</td>
                  <td className="documentation__portfolio-muted">{row.countries.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function DocumentationTab() {
  const { companyId } = useParams()

  return (
    <div className="panel-surface documentation">
      <h3>Documentation</h3>
      <p className="documentation__intro">Generated reports and analyses, organized by category.</p>

      <section className="documentation__category">
        <h4>General Portfolio Directory</h4>
        <ProductPortfolioCategory companyId={companyId} />
      </section>

      <section className="documentation__category">
        <h4>Start-up Investment</h4>
        <StartupInvestmentCategory companyId={companyId} />
      </section>

      <section className="documentation__category">
        <h4>Countries Commercial Profiles</h4>
        <CountryProfilesCategory companyId={companyId} />
      </section>

      <section className="documentation__category">
        <h4>Country Competitiveness Analyses</h4>
        <CompetitivenessAnalysesCategory companyId={companyId} />
      </section>
    </div>
  )
}

export default DocumentationTab
