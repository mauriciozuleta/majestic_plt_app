import { useCallback, useEffect, useState } from 'react'
import {
  fetchTourismImports,
  fetchTourismProviders,
  importTourismFile,
  setTourismProviderEnabled,
  syncTourismProvider,
} from '../../services/tourism'

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('Could not read the file.'))
    reader.readAsDataURL(file)
  })
}

// Provider configuration: status, on/off, connection test, sync of registered datasets, and the licensed WTTC file import.
function ProvidersPanel({ onDataChanged }) {
  const [providers, setProviders] = useState([])
  const [imports, setImports] = useState([])
  const [message, setMessage] = useState('')
  const [file, setFile] = useState(null)
  const [edition, setEdition] = useState('')
  const [unit, setUnit] = useState('percent')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const load = useCallback(async (check = false) => {
    try {
      const [status, history] = await Promise.all([fetchTourismProviders(check), fetchTourismImports()])
      setProviders(status.providers)
      setImports(history.imports)
    } catch (error) {
      setMessage(error.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const toggle = async (provider) => {
    await setTourismProviderEnabled(provider.provider_id, !provider.enabled)
    await load()
    onDataChanged()
  }

  const sync = async (provider) => {
    setBusy(true)
    try {
      const outcome = await syncTourismProvider(provider.provider_id)
      setMessage(`${provider.provider_name}: ${outcome.stored} observation(s) stored. ${outcome.warnings.join(' ')}`)
      await load()
      onDataChanged()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  const upload = async (event) => {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setResult(null)
    try {
      const outcome = await importTourismFile({ provider: 'WTTC', file_name: file.name, content_base64: await readAsBase64(file), dataset_edition: edition, unit })
      setResult(outcome)
      setMessage(`Imported ${outcome.success_count} observation(s), rejected ${outcome.rejected_count}.`)
      await load()
      onDataChanged()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tourism__providers">
      <table className="tourism__table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Status</th>
            <th>Indicators</th>
            <th>Observations</th>
            <th>Last sync</th>
            <th>Enabled</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {providers.map((provider) => (
            <tr key={provider.provider_id}>
              <td>
                {provider.provider_name}
                <small className="tourism__muted"> · {provider.authentication_type.replace('_', ' ')}</small>
              </td>
              <td title={provider.detail || ''}>
                <span className={`tourism__status tourism__status--${provider.connection_status}`}>{provider.connection_status.replace('_', ' ')}</span>
                <small className="tourism__muted"> {provider.detail}</small>
              </td>
              <td>{provider.supported_indicators.length ? provider.supported_indicators.join(', ') : '—'}</td>
              <td>{provider.observations}</td>
              <td>{provider.last_sync ? new Date(provider.last_sync).toLocaleString() : '—'}</td>
              <td>
                <input type="checkbox" checked={provider.enabled} onChange={() => toggle(provider)} aria-label={`Enable ${provider.provider_name}`} />
              </td>
              <td>
                {provider.provider_id === 'WORLD_BANK' && <button type="button" onClick={() => load(true)}>Test connection</button>}
                {(provider.provider_id === 'IDB' || provider.provider_id === 'STATISTA' || provider.provider_id === 'UNSD') && (
                  <button type="button" disabled={busy || provider.connection_status === 'not_configured' || provider.connection_status === 'disabled'} onClick={() => sync(provider)}>
                    {provider.provider_id === 'UNSD' ? 'Sync now' : 'Sync'}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="tourism__import" onSubmit={upload}>
        <strong>Import licensed WTTC data (CSV or XLSX)</strong>
        <input type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        <input placeholder="Dataset edition (e.g. 2025 Economic Impact Research)" value={edition} onChange={(event) => setEdition(event.target.value)} />
        <select value={unit} onChange={(event) => setUnit(event.target.value)}>
          <option value="percent">Values are percent (12.5 = 12.5%)</option>
          <option value="fraction">Values are fractions (0.125 = 12.5%)</option>
        </select>
        <button type="submit" disabled={!file || busy}>
          Import
        </button>
        <small className="tourism__muted">Only files obtained under a WTTC licence. Total contribution shares only: direct-only columns and job counts are rejected.</small>
      </form>

      {message && <p className="tourism__muted">{message}</p>}
      {result && result.validation_report.rejected_total > 0 && (
        <details open>
          <summary>{result.validation_report.rejected_total} rejected row(s)</summary>
          <ul className="tourism__list">
            {result.validation_report.rejected.slice(0, 30).map((row) => (
              <li key={`${row.row}-${row.reason}`}>
                row {row.row}: {row.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      {result?.validation_report.warnings?.map((warning) => (
        <p key={warning} className="tourism__warning">
          {warning}
        </p>
      ))}

      {imports.length > 0 && (
        <details>
          <summary>Import history ({imports.length})</summary>
          <ul className="tourism__list">
            {imports.map((job) => (
              <li key={job.import_id}>
                {new Date(job.import_date).toLocaleString()} · {job.provider} · {job.file_name} · {job.dataset_edition} · {job.success_count} ok / {job.rejected_count} rejected
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export default ProvidersPanel
