import { useEffect, useMemo, useState } from 'react'
import { fetchFuelEvents, fetchFuelPrice, fetchFuelSeries, fetchFuelStat, searchFuelPlaces } from '../../services/fuelPrices'
import { formatCurrencyValue } from '../../utils/currencyFormat'
import FuelChart from './FuelChart'
import FuelSourcesPanel from './FuelSourcesPanel'
import './FuelStatistics.css'

const LEVEL_LABEL = { airport: 'Airport', country: 'Country', region: 'Region', global: 'Global' }
const QUALITY_LABEL = { observed: 'Observed', estimated: 'Estimated', manual: 'Manual', derived: 'Derived' }
const CLASS_LABEL = { scheduled: 'Scheduled', non_scheduled: 'Non-scheduled' }
const STAT_KINDS = ['descriptive', 'volatility', 'seasonality', 'regression', 'lags', 'half_life', 'events']
const RANGES = [{ id: '1y', label: '1 year', years: 1 }, { id: '5y', label: '5 years', years: 5 }, { id: 'all', label: 'All', years: null }]

const usd = (value, digits = 3) => formatCurrencyValue(value, 'USD', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const pct = (value) => (value === null || value === undefined ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}%`)

function fromDate(years) {
  if (!years) return undefined
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

function PriceCard({ cls, result }) {
  const ok = result.status === 'ok'
  return (
    <div className={`fuel-card ${ok ? '' : 'is-empty'}`}>
      <div className="fuel-card__head">
        <strong>{CLASS_LABEL[cls]}</strong>
        {ok && (
          <span className="fuel-badges">
            <span className={`fuel-badge fuel-badge--level-${result.geo_level_used}`}>{LEVEL_LABEL[result.geo_level_used]}</span>
            <span className={`fuel-badge fuel-badge--${result.quality}`}>{QUALITY_LABEL[result.quality]}</span>
          </span>
        )}
      </div>
      {ok ? (
        <>
          <div className="fuel-card__value">{usd(result.value)}<small> / US gal</small></div>
          {result.original?.value != null && result.original.unit !== 'usd_gal' && (
            <div className="fuel-card__muted">Original: {result.original.value} {result.original.unit}</div>
          )}
          <div className="fuel-card__changes">
            {['1w', '1m', '1y'].map((key) => (
              <span key={key}>{key}: <b className={result.changes?.[key]?.pct > 0 ? 'is-up' : 'is-down'}>{pct(result.changes?.[key]?.pct)}</b></span>
            ))}
          </div>
          <div className="fuel-card__muted">
            {result.source_name} · {result.price_basis.replace('_', ' ')} · as of {result.as_of} ({result.freshness_days} days old)
          </div>
          {result.note && <div className="fuel-card__note">{result.note}</div>}
          {result.formula && <div className="fuel-card__note">Formula: {result.formula}</div>}
        </>
      ) : (
        <>
          <p className="fuel-card__empty">{result.message}</p>
          {result.scheduled_reference && (
            <p className="fuel-card__muted">
              For reference only (scheduled, {LEVEL_LABEL[result.scheduled_reference.geo_level_used]} level): {usd(result.scheduled_reference.value)} / gal — this is not a retail price.
            </p>
          )}
        </>
      )}
    </div>
  )
}

function StatBlock({ kind, stat }) {
  if (!stat) return null
  if (stat.status !== 'ok') {
    return <div className="fuel-stat is-refused"><h5>{kind}</h5><p>Not computed: {stat.reason}</p></div>
  }
  const meta = <p className="fuel-stat__meta">n = {stat.n} · {stat.from} → {stat.to} · quality: {Object.entries(stat.quality_mix || {}).map(([k, v]) => `${k} ${v}`).join(', ') || '—'}</p>
  let body = null
  if (kind === 'descriptive') {
    body = <p>Mean {usd(stat.mean)} · median {usd(stat.median)} · std {usd(stat.std)} · min {usd(stat.min.value)} ({stat.min.date}) · max {usd(stat.max.value)} ({stat.max.date}) · p5–p95 {usd(stat.percentiles['5'])}–{usd(stat.percentiles['95'])}</p>
  } else if (kind === 'volatility') {
    body = (
      <p>Weekly {(stat.weekly_vol * 100).toFixed(2)}% · annualised {(stat.annualized_vol * 100).toFixed(1)}%
        {stat.calm.weekly_vol != null && <> · calm {(stat.calm.weekly_vol * 100).toFixed(2)}% (n {stat.calm.n})</>}
        {stat.shock.weekly_vol != null && <> · {stat.shock_window_weeks} weeks after an event {(stat.shock.weekly_vol * 100).toFixed(2)}% (n {stat.shock.n})</>}
        {stat.note && <><br />{stat.note}</>}
      </p>
    )
  } else if (kind === 'seasonality') {
    body = (
      <>
        {stat.warning && <p className="fuel-card__note">{stat.warning}</p>}
        <div className="fuel-season">
          {stat.months.map((row) => (
            <span key={row.month} title={`${row.n_years} years${row.ci95_pct != null ? `, ±${row.ci95_pct.toFixed(1)}%` : ''}`}>
              {['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'][row.month - 1]} <b className={row.effect_pct > 0 ? 'is-up' : 'is-down'}>{row.effect_pct == null ? '—' : pct(row.effect_pct)}</b>
            </span>
          ))}
        </div>
      </>
    )
  } else if (kind === 'regression') {
    body = <p>Jet = {stat.levels.intercept.toFixed(3)} + {stat.levels.slope.toFixed(3)} × Brent (R² {stat.levels.r2?.toFixed(3)}); weekly changes: slope {stat.changes.slope.toFixed(3)} (R² {stat.changes.r2?.toFixed(3)}). {stat.note}</p>
  } else if (kind === 'lags') {
    body = <p>Best lag: Brent leads jet by {stat.best?.lag_weeks} weeks (corr {stat.best?.corr?.toFixed(3)}). Lags tested: {stat.lags_tested_weeks[0]} to {stat.lags_tested_weeks[stat.lags_tested_weeks.length - 1]} weeks.</p>
  } else if (kind === 'half_life') {
    body = <p>Crack spread AR(1) φ = {stat.phi.toFixed(3)} · half-life {stat.half_life_weeks ? `${stat.half_life_weeks.toFixed(1)} weeks` : 'no mean reversion detected'}{stat.long_run_mean != null && <> · long-run mean {usd(stat.long_run_mean)}</>}</p>
  } else if (kind === 'events') {
    body = (
      <ul>
        {stat.events.map((e) => (
          <li key={e.date + e.title}>{e.date} {e.title}: {e.change_pct != null ? `${usd(e.mean_before)} → ${usd(e.mean_after)} (${pct(e.change_pct)}) over ±${stat.weeks} weeks` : e.note}</li>
        ))}
      </ul>
    )
  }
  return <div className="fuel-stat"><h5>{kind.replace('_', ' ')}</h5>{body}{meta}</div>
}

function DriverPanel({ decomposition }) {
  if (!decomposition) return null
  if (decomposition.status !== 'ok') return <div className="fuel-stat is-refused"><h5>Crude vs crack spread</h5><p>Not computed: {decomposition.reason}</p></div>
  const { delta, share_of_change: share, start, end } = decomposition
  const crudePct = share.crude == null ? 0 : Math.max(0, Math.min(100, share.crude * 100))
  return (
    <div className="fuel-stat">
      <h5>What moved the price: crude vs crack spread</h5>
      <p>{start.date} → {end.date}: jet {usd(start.jet)} → {usd(end.jet)} ({usd(delta.jet)}). Crude (Brent) {usd(delta.crude)} · crack spread {usd(start.crack)} → {usd(end.crack)} ({usd(delta.crack)}).</p>
      {share.crude != null && (
        <div className="fuel-split" title="Share of the change">
          <span style={{ width: `${crudePct}%` }}>Crude {(share.crude * 100).toFixed(0)}%</span>
          <span className="is-crack" style={{ width: `${100 - crudePct}%` }}>Crack {(share.crack * 100).toFixed(0)}%</span>
        </div>
      )}
      <p className="fuel-stat__meta">{decomposition.note} Window mean: jet {usd(decomposition.window_mean.jet)}, Brent {usd(decomposition.window_mean.brent)}, crack {usd(decomposition.window_mean.crack)}.</p>
    </div>
  )
}

function FuelStatisticsView() {
  const [tab, setTab] = useState('prices')
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [place, setPlace] = useState({ type: 'country', code: 'US', label: 'United States (US)', country_iso2: 'US' })
  const [classMode, setClassMode] = useState('both')
  const [range, setRange] = useState('5y')
  const [overlay, setOverlay] = useState('none')
  const [price, setPrice] = useState(null)
  const [series, setSeries] = useState({})
  const [overlaySeries, setOverlaySeries] = useState(null)
  const [events, setEvents] = useState([])
  const [stats, setStats] = useState({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const classes = classMode === 'both' ? ['scheduled', 'non_scheduled'] : [classMode]
  const from = useMemo(() => fromDate(RANGES.find((r) => r.id === range)?.years), [range])
  const placeArgs = useMemo(() => (place.type === 'airport' ? { airport: place.code, country: place.country_iso2 } : { country: place.code }), [place])

  useEffect(() => {
    if (query.trim().length < 2) {
      setSuggestions([])
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(() => searchFuelPlaces(query.trim()).then((rows) => !cancelled && setSuggestions(rows)).catch(() => {}), 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    fetchFuelEvents().then(setEvents).catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    const run = async () => {
      try {
        const priceResult = await fetchFuelPrice({ ...placeArgs, operatorClass: classMode })
        const seriesResults = {}
        for (const cls of classes) {
          // eslint-disable-next-line no-await-in-loop
          seriesResults[cls] = await fetchFuelSeries({ ...placeArgs, operatorClass: cls, from })
        }
        const statResults = {}
        const baseArgs = { ...placeArgs, operatorClass: classes[0], from }
        for (const kind of STAT_KINDS) {
          // eslint-disable-next-line no-await-in-loop
          statResults[kind] = await fetchFuelStat(kind, baseArgs)
        }
        statResults.decomposition = await fetchFuelStat('decomposition', { ...placeArgs, operatorClass: classes[0], from: fromDate(1) })
        if (!cancelled) {
          setPrice(priceResult)
          setSeries(seriesResults)
          setStats(statResults)
        }
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- classes derives from classMode
  }, [placeArgs, classMode, from])

  useEffect(() => {
    if (overlay === 'none') {
      setOverlaySeries(null)
      return
    }
    fetchFuelSeries({ kind: 'driver', driver: 'brent', from }).then((s) => {
      if (overlay === 'brent') return setOverlaySeries(s.points)
      const jet = new Map((series.scheduled?.points || []).map((p) => [p.date, p.value]))
      return setOverlaySeries(s.points.filter((p) => jet.has(p.date)).map((p) => ({ date: p.date, value: jet.get(p.date) - p.value })))
    }).catch(() => setOverlaySeries(null))
  }, [overlay, from, series])

  const pick = (row) => {
    setPlace(row)
    setQuery('')
    setSuggestions([])
  }
  const resolvedNote = price?.place ? `${price.place.airport ? `${price.place.airport} · ` : ''}${price.place.country || ''}${price.place.region ? ` · region ${price.place.region}` : ''}` : ''
  const mainSeries = series[classes[0]]

  return (
    <div className="fuel-stats">
      <div className="fuel-stats__tabs">
        <button type="button" className={tab === 'prices' ? 'is-active' : ''} onClick={() => setTab('prices')}>Prices &amp; statistics</button>
        <button type="button" className={tab === 'data' ? 'is-active' : ''} onClick={() => setTab('data')}>Data coverage &amp; sources</button>
      </div>

      {tab === 'data' ? <FuelSourcesPanel /> : (
        <>
          <div className="fuel-toolbar">
            <div className="fuel-search">
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Country, ISO code or IATA code (MIA, BOG…)" aria-label="Search place" />
              {suggestions.length > 0 && (
                <ul>
                  {suggestions.map((row) => <li key={`${row.type}-${row.code}`}><button type="button" onClick={() => pick(row)}>{row.label}</button></li>)}
                </ul>
              )}
            </div>
            <div className="fuel-seg">
              {[['both', 'Both'], ['scheduled', 'Scheduled'], ['non_scheduled', 'Non-scheduled']].map(([id, label]) => (
                <button key={id} type="button" className={classMode === id ? 'is-active' : ''} onClick={() => setClassMode(id)}>{label}</button>
              ))}
            </div>
            <div className="fuel-seg">
              {RANGES.map((r) => <button key={r.id} type="button" className={range === r.id ? 'is-active' : ''} onClick={() => setRange(r.id)}>{r.label}</button>)}
            </div>
          </div>

          <p className="fuel-place">Showing: <b>{place.label}</b>{resolvedNote && <span> ({resolvedNote})</span>}</p>
          {error && <p className="fuel-stats__error">{error}</p>}
          {loading && <p className="fuel-stats__empty">Loading…</p>}

          {price && (
            <div className="fuel-cards">
              {classes.map((cls) => price.results[cls] && <PriceCard key={cls} cls={cls} result={price.results[cls]} />)}
            </div>
          )}

          <div className="fuel-chart-box">
            <div className="fuel-chart-box__head">
              <h4>Price history (USD per US gallon) — {CLASS_LABEL[classes[0]]}</h4>
              <label>Second line
                <select value={overlay} onChange={(e) => setOverlay(e.target.value)}>
                  <option value="none">None</option>
                  <option value="brent">Brent</option>
                  <option value="crack">Crack spread (jet − Brent)</option>
                </select>
              </label>
            </div>
            {mainSeries?.points?.length ? (
              <>
                <FuelChart primary={mainSeries.points} secondary={overlaySeries} secondaryLabel={overlay} events={events} />
                <p className="fuel-stat__meta">Series {mainSeries.series_id} · {mainSeries.period_type} · quality {Object.entries(mainSeries.quality_mix).map(([k, v]) => `${k} ${v}`).join(', ')}. Vertical lines mark events ({events.map((e) => e.title).join('; ') || 'none'}).</p>
              </>
            ) : (
              <p className="fuel-stats__empty">
                {classes[0] === 'non_scheduled' ? 'No observed non-scheduled (retail) series for this place.' : 'No series for this place from an enabled source.'} Enable a source or import data in “Data coverage &amp; sources”.
              </p>
            )}
          </div>

          <div className="fuel-stat-grid">
            <DriverPanel decomposition={stats.decomposition} />
            {STAT_KINDS.map((kind) => <StatBlock key={kind} kind={kind} stat={stats[kind]} />)}
          </div>
        </>
      )}
    </div>
  )
}

export default FuelStatisticsView
