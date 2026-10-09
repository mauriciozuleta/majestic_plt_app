import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchTourismCompare, fetchTourismCountries, fetchTourismCountry, fetchTourismHistory, tourismExportUrl } from '../../services/tourism'
import CountrySelector, { loadSavedSelection } from './CountrySelector'
import ProvidersPanel from './ProvidersPanel'
import { BarChart, LineChart } from './TourismCharts'
import { STATUS_CLASS, TOURISM_INDICATORS, cellTooltip, formatTourismValue } from './tourismFormat'
import './TourismDependencyView.css'

const DEFAULT_SELECTION = ['JM', 'BB', 'BS']
const PAGE_SIZES = [10, 25, 50]
const COLUMN_OPTIONS = [
  ...TOURISM_INDICATORS.map((indicator) => ({ key: indicator.code, label: indicator.label })),
  { key: 'GDP_USD', label: 'GDP USD' },
  { key: 'region', label: 'Region' },
  { key: 'status', label: 'Status' },
]
const currentYear = new Date().getFullYear()

// Tools ▸ Tourism & Economic Dependency: compare tourism's weight in any country's economy from World Bank data, licensed WTTC files and optional IDB/Statista datasets.
function TourismDependencyView() {
  const [registry, setRegistry] = useState([])
  const [regions, setRegions] = useState([])
  const [selected, setSelected] = useState(() => loadSavedSelection() ?? DEFAULT_SELECTION)
  const [yearMode, setYearMode] = useState('latest')
  const [yearValue, setYearValue] = useState(currentYear - 2)
  const [rangeFrom, setRangeFrom] = useState(2000)
  const [rangeTo, setRangeTo] = useState(currentYear - 1)
  const [rows, setRows] = useState([])
  const [warnings, setWarnings] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  const [sort, setSort] = useState({ key: 'country', direction: 'asc' })
  const [filter, setFilter] = useState('')
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(0)
  const [hiddenColumns, setHiddenColumns] = useState(() => new Set(['GDP_USD', 'status']))
  const [showColumns, setShowColumns] = useState(false)

  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [histories, setHistories] = useState([])
  const [exportLayout, setExportLayout] = useState('wide')

  const compareYear = yearMode === 'latest' ? 'latest' : yearMode === 'year' ? yearValue : rangeTo
  const historyFrom = yearMode === 'range' ? rangeFrom : 2000
  const historyTo = yearMode === 'range' ? rangeTo : currentYear

  const loadRegistry = useCallback(async () => {
    const data = await fetchTourismCountries()
    setRegistry(data.countries)
    setRegions(data.regions)
  }, [])

  useEffect(() => {
    loadRegistry().catch((err) => setError(err.message))
  }, [loadRegistry])

  // comparison table: reload (debounced) when the selection, the year or a data change asks for it
  useEffect(() => {
    if (selected.length === 0) {
      setRows([])
      setWarnings([])
      return undefined
    }
    let cancelled = false
    setLoading(true)
    const timer = setTimeout(() => {
      fetchTourismCompare(selected, compareYear)
        .then((data) => {
          if (cancelled) return
          setRows(data.rows)
          setWarnings(data.warnings)
          setError('')
        })
        .catch((err) => !cancelled && setError(err.message))
        .finally(() => !cancelled && setLoading(false))
    }, 350)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [selected, compareYear, reload])

  // historical dependency lines (first 8 selected countries)
  useEffect(() => {
    let cancelled = false
    const ids = selected.slice(0, 8)
    Promise.all(ids.map((id) => fetchTourismHistory(id, historyFrom, historyTo).catch(() => null))).then((results) => {
      if (cancelled) return
      setHistories(
        results
          .filter(Boolean)
          .map((history) => ({ label: history.country.country, points: history.series.TOURISM_DEPENDENCY.filter((point) => point.value != null) })),
      )
    })
    return () => {
      cancelled = true
    }
  }, [selected, historyFrom, historyTo, reload])

  const sortValue = (row, key) => {
    if (key === 'country') return row.country
    if (key === 'region') return row.region
    return row.indicators[key]?.value ?? null
  }

  const visibleRows = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    const filtered = rows.filter((row) => !needle || row.country.toLowerCase().includes(needle) || row.region.toLowerCase().includes(needle) || row.iso_alpha3?.toLowerCase() === needle)
    const direction = sort.direction === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      const left = sortValue(a, sort.key)
      const right = sortValue(b, sort.key)
      if (left == null && right == null) return 0
      if (left == null) return 1
      if (right == null) return -1
      return (typeof left === 'string' ? left.localeCompare(right) : left - right) * direction
    })
  }, [rows, filter, sort])

  const pages = Math.max(1, Math.ceil(visibleRows.length / pageSize))
  const pageRows = visibleRows.slice(page * pageSize, page * pageSize + pageSize)
  useEffect(() => setPage(0), [filter, pageSize, selected])

  const header = (key, label, title) => (
    <th key={key} title={title} className="is-sortable" onClick={() => setSort((current) => ({ key, direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc' }))}>
      {label}
      {sort.key === key ? (sort.direction === 'asc' ? ' ▲' : ' ▼') : ''}
    </th>
  )

  const openDetail = async (row) => {
    setDetailLoading(true)
    setDetail({ row })
    try {
      const [info, history] = await Promise.all([fetchTourismCountry(row.country_id, compareYear), fetchTourismHistory(row.country_id, historyFrom, historyTo)])
      setDetail({ row: info.row, warnings: info.warnings, observations: info.observations, history })
    } catch (err) {
      setDetail({ row, warnings: [err.message] })
    } finally {
      setDetailLoading(false)
    }
  }

  const exportLink = (format) =>
    tourismExportUrl({ codes: selected, year: compareYear, format, layout: exportLayout, from: yearMode === 'range' ? rangeFrom : undefined, to: yearMode === 'range' ? rangeTo : undefined })

  const barItems = (code) => rows.map((row) => ({ label: row.country, value: row.indicators[code].value, year: row.indicators[code].year }))

  return (
    <section className="tourism">
      <header className="tourism__header">
        <h3>Global Tourism & Economic Dependency</h3>
        <p>
          Tourism contribution, receipts and population for any country or territory. Values come from the World Bank, licensed WTTC files and optional IDB/Statista datasets; nothing is estimated, and every
          value shows its own year and source.
        </p>
      </header>

      <div className="panel-surface tourism__panel">
        <h4>1 · Countries</h4>
        <CountrySelector registry={registry} regions={regions} selected={selected} onChange={setSelected} onRegistryChanged={loadRegistry} />
      </div>

      <div className="panel-surface tourism__panel">
        <h4>2 · Reference year</h4>
        <div className="tourism__year">
          {[
            ['latest', 'Latest available'],
            ['year', 'Specific year'],
            ['range', 'Historical range'],
          ].map(([mode, label]) => (
            <label key={mode}>
              <input type="radio" name="tourism-year-mode" checked={yearMode === mode} onChange={() => setYearMode(mode)} /> {label}
            </label>
          ))}
          {yearMode === 'year' && <input type="number" min="1960" max="2100" value={yearValue} onChange={(event) => setYearValue(Number(event.target.value))} />}
          {yearMode === 'range' && (
            <>
              <input type="number" min="1960" max="2100" value={rangeFrom} onChange={(event) => setRangeFrom(Number(event.target.value))} />
              <span>to</span>
              <input type="number" min="1960" max="2100" value={rangeTo} onChange={(event) => setRangeTo(Number(event.target.value))} />
              <small className="tourism__muted">The table shows {rangeTo}; the line chart covers the whole range.</small>
            </>
          )}
          {yearMode === 'latest' && <small className="tourism__muted">Each value shows the year it actually refers to.</small>}
        </div>
      </div>

      <div className="panel-surface tourism__panel">
        <div className="tourism__table-head">
          <h4>3 · Comparison</h4>
          <input type="search" placeholder="Filter countries / regions…" value={filter} onChange={(event) => setFilter(event.target.value)} />
          <button type="button" onClick={() => setShowColumns((value) => !value)}>
            Columns
          </button>
          <button type="button" onClick={() => setReload((value) => value + 1)}>
            Refresh
          </button>
          <span className="tourism__spacer" />
          <select value={exportLayout} onChange={(event) => setExportLayout(event.target.value)} aria-label="Export layout">
            <option value="wide">One row per country</option>
            <option value="long">One row per country-year-indicator</option>
          </select>
          {['csv', 'xlsx', 'json'].map((format) => (
            <a key={format} className={`tourism__button ${selected.length === 0 ? 'is-disabled' : ''}`} href={selected.length ? exportLink(format) : undefined} download>
              {format.toUpperCase()}
            </a>
          ))}
        </div>
        {showColumns && (
          <div className="tourism__columns">
            {COLUMN_OPTIONS.map((column) => (
              <label key={column.key}>
                <input
                  type="checkbox"
                  checked={!hiddenColumns.has(column.key)}
                  onChange={() =>
                    setHiddenColumns((current) => {
                      const next = new Set(current)
                      if (next.has(column.key)) next.delete(column.key)
                      else next.add(column.key)
                      return next
                    })
                  }
                />{' '}
                {column.label}
              </label>
            ))}
          </div>
        )}
        {error && <p className="tourism__error">{error}</p>}
        {warnings.map((warning) => (
          <p key={warning} className="tourism__warning">
            {warning}
          </p>
        ))}
        {loading && <p className="tourism__muted">Loading from the providers…</p>}

        <div className="tourism__scroll">
          <table className="tourism__table">
            <thead>
              <tr>
                {header('country', 'Country')}
                {!hiddenColumns.has('region') && header('region', 'Region')}
                {TOURISM_INDICATORS.filter((indicator) => !hiddenColumns.has(indicator.code)).map((indicator) => header(indicator.code, indicator.label, indicator.title))}
                {!hiddenColumns.has('GDP_USD') && header('GDP_USD', 'GDP USD', 'GDP, current US$ (denominator of the dependency)')}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <tr key={row.country_id} className={detail?.row?.country_id === row.country_id ? 'is-selected' : ''} onClick={() => openDetail(row)}>
                  <td>
                    <button type="button" className="tourism__link">
                      {row.country}
                    </button>
                    {row.territory_status === 'territory' && <small className="tourism__tag">territory</small>}
                  </td>
                  {!hiddenColumns.has('region') && <td>{row.region}</td>}
                  {[...TOURISM_INDICATORS.filter((indicator) => !hiddenColumns.has(indicator.code)), ...(hiddenColumns.has('GDP_USD') ? [] : [{ code: 'GDP_USD', kind: 'usd' }])].map((indicator) => {
                    const cell = row.indicators[indicator.code]
                    return (
                      <td key={indicator.code} className={`tourism__num ${cell.value == null ? 'is-na' : ''}`} title={cellTooltip(cell)}>
                        {formatTourismValue(indicator.kind, cell.value)}
                        {cell.value != null && (
                          <small className="tourism__year-tag">
                            {cell.year}
                            {!hiddenColumns.has('status') && <i className={`tourism__dot ${STATUS_CLASS[cell.status] || ''}`} title={cell.status} />}
                          </small>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={9} className="tourism__muted">
                    {selected.length === 0 ? 'Select at least one country.' : 'No rows.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="tourism__pager">
          <span>{visibleRows.length} countries</span>
          <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size} per page
              </option>
            ))}
          </select>
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
            ‹
          </button>
          <span>
            {page + 1} / {pages}
          </span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
            ›
          </button>
        </div>
      </div>

      {detail && (
        <div className="panel-surface tourism__panel">
          <div className="tourism__table-head">
            <h4>
              Details · {detail.row.country} {detailLoading && <small className="tourism__muted">loading…</small>}
            </h4>
            <span className="tourism__spacer" />
            <button type="button" onClick={() => setDetail(null)}>
              Close
            </button>
          </div>
          <table className="tourism__table">
            <thead>
              <tr>
                <th>Indicator</th>
                <th>Value</th>
                <th>Year</th>
                <th>Provider</th>
                <th>Dataset / edition</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {[...TOURISM_INDICATORS, { code: 'GDP_USD', label: 'GDP USD (denominator)', kind: 'usd' }].map((indicator) => {
                const cell = detail.row.indicators[indicator.code]
                return (
                  <tr key={indicator.code}>
                    <td>{indicator.label}</td>
                    <td className="tourism__num">{formatTourismValue(indicator.kind, cell.value)}</td>
                    <td>{cell.year ?? '—'}</td>
                    <td>{cell.url ? <a href={cell.url} target="_blank" rel="noreferrer">{cell.source}</a> : cell.source || '—'}</td>
                    <td>
                      {cell.dataset || '—'}
                      {cell.edition ? ` · ${cell.edition}` : ''}
                    </td>
                    <td>
                      <span className={`tourism__badge ${STATUS_CLASS[cell.status] || ''}`}>{cell.status}</span>
                      {cell.value == null && <small className="tourism__muted"> {cell.reason}</small>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {detail.row.indicators.TOURISM_DEPENDENCY.value != null && (
            <p className="tourism__muted">Calculation: {detail.row.indicators.TOURISM_DEPENDENCY.note}</p>
          )}
          {detail.warnings?.length > 0 && (
            <details>
              <summary>Missing-data and quality warnings ({detail.warnings.length})</summary>
              <ul className="tourism__list">
                {detail.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          {detail.history && (
            <LineChart
              title={`${detail.row.country} — receipts / GDP over time (${historyFrom}–${historyTo})`}
              series={[{ label: 'Tourism dependency %', points: detail.history.series.TOURISM_DEPENDENCY.filter((point) => point.value != null) }]}
              format={(value) => formatTourismValue('pct', value)}
            />
          )}
          {detail.observations && (
            <details>
              <summary>All stored observations ({detail.observations.length}) — source traceability</summary>
              <div className="tourism__scroll">
                <table className="tourism__table">
                  <thead>
                    <tr>
                      <th>Indicator</th>
                      <th>Year</th>
                      <th>Value</th>
                      <th>Source</th>
                      <th>Edition</th>
                      <th>Status</th>
                      <th>Retrieved</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.observations.slice(0, 400).map((obs) => (
                      <tr key={`${obs.indicator}-${obs.year}-${obs.source}-${obs.edition}`}>
                        <td>{obs.indicator}</td>
                        <td>{obs.year}</td>
                        <td className="tourism__num">{obs.value}</td>
                        <td>{obs.source}</td>
                        <td>{obs.edition || '—'}</td>
                        <td>{obs.status}</td>
                        <td>{new Date(obs.retrieved_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}

      <div className="panel-surface tourism__panel">
        <h4>4 · Charts</h4>
        <div className="tourism__charts">
          <BarChart title="Tourism GDP contribution — total (WTTC, % of GDP)" items={barItems('TOURISM_GDP_TOTAL_PCT')} format={(v) => formatTourismValue('pct', v)} color="#14b8a6" />
          <BarChart title="Tourism direct GDP (UN SDG 8.9.1, % of GDP)" items={barItems('TOURISM_GDP_DIRECT_PCT')} format={(v) => formatTourismValue('pct', v)} color="#2dd4bf" />
          <BarChart title="Tourism employment dependency (WTTC, % of employment)" items={barItems('TOURISM_EMPLOYMENT')} format={(v) => formatTourismValue('pct', v)} color="#60a5fa" />
          <BarChart title="International tourism receipts (USD)" items={barItems('TOURISM_RECEIPTS')} format={(v) => formatTourismValue('usd', v, { short: true })} color="#f59e0b" />
          <BarChart title="Tourism receipts / GDP dependency (%)" items={barItems('TOURISM_DEPENDENCY')} format={(v) => formatTourismValue('pct', v)} color="#c084fc" />
          <BarChart title="Population" items={barItems('POPULATION')} format={(v) => formatTourismValue('count', v, { short: true })} color="#34d399" />
          <LineChart title={`Historical tourism dependency (receipts / GDP %, ${historyFrom}–${historyTo})`} series={histories} format={(v) => formatTourismValue('pct', v)} />
        </div>
      </div>

      <div className="panel-surface tourism__panel">
        <h4>5 · Providers</h4>
        <ProvidersPanel onDataChanged={() => setReload((value) => value + 1)} />
      </div>
    </section>
  )
}

export default TourismDependencyView
