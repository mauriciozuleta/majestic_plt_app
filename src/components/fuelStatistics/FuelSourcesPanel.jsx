import { useCallback, useEffect, useState } from 'react'
import { fetchFuelCoverage, fetchFuelSources, importBtsCsv, importFuelCsv, importIataCsv, refreshFuelSource, setFuelSourceEnabled } from '../../services/fuelPrices'

const STATUS_LABEL = { verified_ok: 'Terms verified', unverified: 'Terms unverified', restricted: 'Restricted' }
const IMPORTERS = {
  manual_csv: { label: 'Prices CSV (obs_date, value, unit, geo_level, operator_class, price_basis, country_iso2, airport_iata, region_code…)', run: importFuelCsv },
  iata_regional: { label: 'IATA regional CSV (obs_date, region, usd_bbl | cts_gal | usd_mt)', run: importIataCsv },
  bts_p12: { label: 'BTS P-12(a) CSV download (YEAR, MONTH and the gallons/cost columns)', run: importBtsCsv },
}

function SourceRow({ source, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const importer = IMPORTERS[source.id]

  const toggle = async () => {
    let signedOffBy
    if (!source.enabled && source.terms_status !== 'verified_ok') {
      const terms = source.license_terms_url ? `\nTerms: ${source.license_terms_url}` : '\nNo terms URL is on record.'
      const summary = source.notes ? `\n\nSummary: ${source.notes}` : ''
      signedOffBy = window.prompt(`“${source.name}” has terms status “${source.terms_status}”.${terms}${summary}\n\nType your name to confirm you reviewed the terms and allow its use:`)
      if (!signedOffBy) return
    }
    setBusy(true)
    try {
      await setFuelSourceEnabled(source.id, !source.enabled, signedOffBy)
      setMessage('')
      await onChanged()
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const refresh = async () => {
    setBusy(true)
    setMessage('Downloading — the first full history can take a minute…')
    const result = await refreshFuelSource(source.id, source.observations === 0).catch((e) => ({ ok: false, error: e.message }))
    setMessage(result.ok ? `Fetched ${result.fetched} rows (new ${result.inserted}, updated ${result.updated})` : `Failed: ${result.error}`)
    setBusy(false)
    onChanged()
  }

  const upload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    try {
      const result = await importer.run(await file.text())
      setMessage(`Imported: new ${result.inserted}, updated ${result.updated}${result.implied_bbl_per_mt ? `, implied bbl/mt ${result.implied_bbl_per_mt}` : ''}`)
      onChanged()
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  const stub = source.id.endsWith('_stub')
  return (
    <tr>
      <td>
        <b>{source.name}</b>
        <div className="fuel-card__muted">{source.coverage}</div>
        {source.notes && <div className="fuel-card__muted">{source.notes}</div>}
        {source.license_terms_url && <a href={source.license_terms_url} target="_blank" rel="noreferrer">terms</a>}
        {source.attribution && <div className="fuel-card__muted">{source.attribution}</div>}
        {source.drop_folder && source.enabled && <div className="fuel-card__muted">Drop folder: {source.drop_folder}</div>}
      </td>
      <td><span className={`fuel-badge fuel-badge--terms-${source.terms_status}`}>{STATUS_LABEL[source.terms_status]}</span>{source.terms_signed_off_by && <div className="fuel-card__muted">sign-off: {source.terms_signed_off_by}</div>}</td>
      <td>{source.enabled ? 'Enabled' : 'Disabled'}</td>
      <td>{source.observations}</td>
      <td>{source.last_success_at ? String(source.last_success_at).slice(0, 16).replace('T', ' ') : '—'}{source.last_error && <div className="fuel-stats__error">{source.last_error}</div>}</td>
      <td className="fuel-actions">
        {!stub && <button type="button" disabled={busy || source.terms_status === 'restricted'} onClick={toggle}>{source.enabled ? 'Disable' : 'Enable…'}</button>}
        {source.automatic && source.enabled && <button type="button" disabled={busy} onClick={refresh}>{source.observations === 0 ? 'Download data' : 'Refresh'}</button>}
        {importer && source.enabled && (
          <label className="fuel-upload" title={importer.label}>
            Import CSV
            <input type="file" accept=".csv,text/csv" disabled={busy} onChange={upload} hidden />
          </label>
        )}
        {message && <div className="fuel-card__muted">{message}</div>}
      </td>
    </tr>
  )
}

function FuelSourcesPanel() {
  const [sources, setSources] = useState([])
  const [coverage, setCoverage] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([fetchFuelSources(), fetchFuelCoverage()])
      setSources(s)
      setCoverage(c)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="fuel-sources">
      {error && <p className="fuel-stats__error">{error}</p>}
      <h4>Sources</h4>
      <p className="fuel-card__muted">
        Every source starts disabled unless its terms are verified. Enabling one whose terms are unverified asks for your name as a recorded sign-off. A disabled source’s data disappears from every price, chart and statistic.
      </p>
      <div className="fuel-table-wrap">
        <table className="fuel-table">
          <thead><tr><th>Source</th><th>Terms</th><th>State</th><th>Observations</th><th>Last success</th><th /></tr></thead>
          <tbody>{sources.map((s) => <SourceRow key={s.id} source={s} onChanged={load} />)}</tbody>
        </table>
      </div>

      <h4>Data coverage</h4>
      {coverage?.reminders?.map((r) => (
        <p key={r.source} className="fuel-warning">
          Monthly reminder: {r.message} Latest imported month: {r.latest_imported || 'none'}. <a href={r.url} target="_blank" rel="noreferrer">Open TranStats</a> · folder: {r.drop_folder}
        </p>
      ))}
      {coverage?.stale?.map((j) => (
        <p key={`${j.source}-${j.job}`} className="fuel-warning">
          {j.status === 'error' ? 'Failing' : 'Stale'}: {j.source} / {j.label || j.job} ({j.frequency}) — {j.detail}
        </p>
      ))}
      {coverage && (
        <>
          {coverage.jobs.length > 0 && (
            <div className="fuel-table-wrap">
              <table className="fuel-table">
                <thead><tr><th>Scheduled job</th><th>Runs</th><th>Status</th><th>Newest data</th><th>Last success</th></tr></thead>
                <tbody>
                  {coverage.jobs.map((j) => (
                    <tr key={`${j.source}-${j.job}`}>
                      <td>{j.source} / {j.label || j.job}</td><td>{j.frequency}</td>
                      <td><span className={`fuel-badge fuel-badge--job-${j.status}`}>{j.status.replace('_', ' ')}</span>{j.detail && <div className="fuel-card__muted">{j.detail}</div>}</td>
                      <td>{j.latest_data || '—'}</td><td>{j.last_success_at ? String(j.last_success_at).slice(0, 16).replace('T', ' ') : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="fuel-card__muted">
            {coverage.places.length} series with observed data from enabled sources, out of {coverage.countries_total} countries; everything else falls back to the region or global index, a labelled estimate, or “no data”.
          </p>
          <div className="fuel-table-wrap">
            <table className="fuel-table">
              <thead><tr><th>Level</th><th>Place</th><th>Class</th><th>Observations</th><th>Latest</th></tr></thead>
              <tbody>
                {coverage.places.length === 0 && <tr><td colSpan={5}>No observed data yet. Enable a source and download or import data.</td></tr>}
                {coverage.places.map((p) => (
                  <tr key={`${p.geo_level}-${p.country}-${p.airport}-${p.region}-${p.operator_class}`}>
                    <td>{p.geo_level}</td><td>{p.airport || p.country || p.region || 'Global'}</td><td>{p.operator_class}</td><td>{p.observations}</td><td>{p.latest}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {coverage.disabled_sources.length > 0 && <p className="fuel-card__muted">Disabled pending review: {coverage.disabled_sources.map((s) => `${s.name} (${s.terms_status})`).join('; ')}</p>}
        </>
      )}
    </div>
  )
}

export default FuelSourcesPanel
