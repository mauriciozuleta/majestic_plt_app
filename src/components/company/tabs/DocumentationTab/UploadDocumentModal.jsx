import { useRef, useState } from 'react'
import { INDEXABLE_EXTENSIONS, isIndexable, uploadDocument } from '../../../../services/documents'
import { formatBytes } from './documentFormat'
import './KnowledgeBase.css'

// Two ways in: plain upload (stored for people to consult/download) or
// upload + add to the knowledge base (also turned into a searchable RAG
// index so the API can answer questions from it).
function UploadDocumentModal({ onClose, onUploaded }) {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [busyMode, setBusyMode] = useState(null)
  const [error, setError] = useState('')

  const canIndex = file ? isIndexable(file.name) : false

  const handleSubmit = async (addToKnowledgeBase) => {
    if (!file) return
    setBusyMode(addToKnowledgeBase ? 'knowledge' : 'plain')
    setError('')
    try {
      await uploadDocument(file, addToKnowledgeBase)
      onUploaded()
      onClose()
    } catch (err) {
      setError(err.message || 'Could not upload the document.')
      setBusyMode(null)
    }
  }

  return (
    <div className="kb-modal__overlay" onClick={busyMode ? undefined : onClose}>
      <div className="kb-modal" onClick={(event) => event.stopPropagation()}>
        <header className="kb-modal__header">
          <h3>Upload document</h3>
          <button type="button" className="documentation__link-btn" onClick={onClose} disabled={Boolean(busyMode)}>
            Close
          </button>
        </header>

        <div className="kb-modal__body">
          <button type="button" className="kb-modal__picker" onClick={() => inputRef.current?.click()} disabled={Boolean(busyMode)}>
            {file ? 'Choose a different file' : 'Choose a file'}
          </button>
          <input
            ref={inputRef}
            type="file"
            style={{ display: 'none' }}
            onChange={(event) => {
              const chosen = event.target.files?.[0]
              event.target.value = ''
              if (chosen) {
                setFile(chosen)
                setError('')
              }
            }}
          />

          {file ? (
            <div className="kb-modal__file">
              <strong>{file.name}</strong>
              <span>{formatBytes(file.size)}</span>
            </div>
          ) : (
            <p className="documentation__hint">Up to 25 MB.</p>
          )}

          <ul className="kb-modal__options">
            <li>
              <strong>Upload</strong> — saved in Uploaded Documents for people to consult and download.
            </li>
            <li>
              <strong>Upload and add to knowledge base</strong> — also converted into a searchable index shared by the
              whole portfolio. Commercial profiles and competitiveness analyses are built on the documents here (a
              business plan, for example), and it can answer questions. Works with {INDEXABLE_EXTENSIONS.join(', ')}.
            </li>
          </ul>

          {file && !canIndex && (
            <p className="documentation__hint">This file type can be uploaded, but not added to the knowledge base.</p>
          )}
          {error && <p className="documentation__hint documentation__hint--error">{error}</p>}
        </div>

        <footer className="kb-modal__footer">
          <button
            type="button"
            className="documentation__link-btn"
            onClick={() => handleSubmit(false)}
            disabled={!file || Boolean(busyMode)}
          >
            {busyMode === 'plain' ? 'Uploading…' : 'Upload'}
          </button>
          <button
            type="button"
            className="kb-modal__primary"
            onClick={() => handleSubmit(true)}
            disabled={!file || !canIndex || Boolean(busyMode)}
          >
            {busyMode === 'knowledge' ? 'Indexing…' : 'Upload and add to knowledge base'}
          </button>
        </footer>
      </div>
    </div>
  )
}

export default UploadDocumentModal
