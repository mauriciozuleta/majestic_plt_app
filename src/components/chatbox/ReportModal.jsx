import { useState } from 'react'
import { saveLocalReport } from '../../services/localModels'

// A report built by a local model, in a larger window — to read, copy, or save
// as a Markdown file in the country's `reports` folder.
function ReportModal({ report, onClose }) {
  const [saved, setSaved] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(report.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      setError('Could not copy — select the text and copy it by hand.')
    }
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      setSaved(await saveLocalReport({ country: report.country, model: report.model, request: report.request, text: report.text }))
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="report-modal__overlay" role="dialog" aria-modal="true" aria-label="Report">
      <div className="report-modal">
        <header className="report-modal__header">
          <div>
            <span className="report-modal__eyebrow">Report · {report.country}</span>
            <h3>{report.text.match(/^#+\s*(.+)$/m)?.[1] ?? `${report.country} report`}</h3>
            <p className="report-modal__meta">
              Built by {report.model} from {report.country}’s baked RAG files
            </p>
          </div>
          <button type="button" className="report-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        {report.request && <p className="report-modal__request">“{report.request}”</p>}
        <div className="report-modal__text" tabIndex={0}>
          {report.text}
        </div>
        {report.sources?.length > 0 && <p className="report-modal__sources">From: {report.sources.join(' · ')}</p>}
        {error && <p className="report-modal__error">{error}</p>}
        {saved && (
          <p className="report-modal__ok">
            Saved as <code>{saved.file}</code> in <code>{saved.folder}/</code>
          </p>
        )}
        <footer className="report-modal__footer">
          <button type="button" onClick={copy}>
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
          <button type="button" className="report-modal__primary" onClick={save} disabled={saving || Boolean(saved)}>
            {saved ? 'Saved ✓' : saving ? 'Saving…' : `Save to ${report.country} folder`}
          </button>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default ReportModal
