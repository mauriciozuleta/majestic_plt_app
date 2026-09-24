import { useEffect, useState } from 'react'
import {
  addDocumentToKnowledgeBase,
  askKnowledgeBase,
  deleteDocument,
  documentDownloadUrl,
  fetchDocuments,
  isIndexable,
} from '../../../../services/documents'
import { formatBytes, formatDocumentDate } from './documentFormat'
import './KnowledgeBase.css'

function DocumentRow({ document, onChanged }) {
  const [busy, setBusy] = useState(false)

  const run = async (action, failure) => {
    setBusy(true)
    try {
      await action()
      onChanged()
    } catch (error) {
      window.alert(error.message || failure)
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = () => {
    if (!window.confirm(`Delete "${document.original_filename}"? This can't be undone.`)) return
    run(() => deleteDocument(document.id), 'Could not delete the document.')
  }

  return (
    <div className="documentation__link-row">
      <div className="kb-row__info">
        <span className="documentation__link-name">{document.name}</span>
        <span className="kb-row__meta">
          {document.source === 'report' && <span className="kb-badge kb-badge--report">Report</span>}
          {document.in_knowledge_base && <span>{document.chunk_count} indexed parts</span>}
          <span>{formatBytes(document.size_bytes)}</span>
          <span>{formatDocumentDate(document.uploaded_at)}</span>
          {document.source === 'upload' && <span>{document.original_filename}</span>}
        </span>
      </div>
      <div className="documentation__link-actions">
        <a className="documentation__link-btn" href={documentDownloadUrl(document.id)} download>
          Download
        </a>
        {!document.in_knowledge_base && isIndexable(document.original_filename) && (
          <button
            type="button"
            className="documentation__link-btn"
            disabled={busy}
            onClick={() => run(() => addDocumentToKnowledgeBase(document.id), 'Could not add to the knowledge base.')}
          >
            {busy ? 'Indexing…' : 'Add to knowledge base'}
          </button>
        )}
        {document.source === 'upload' && (
          <button type="button" className="documentation__link-btn kb-btn--danger" disabled={busy} onClick={handleDelete}>
            Delete
          </button>
        )}
      </div>
    </div>
  )
}

function AskKnowledgeBase() {
  const [question, setQuestion] = useState('')
  const [state, setState] = useState({ status: 'idle', answer: '', sources: [], error: '' })

  const handleAsk = async (event) => {
    event.preventDefault()
    if (!question.trim()) return
    setState({ status: 'asking', answer: '', sources: [], error: '' })
    try {
      const result = await askKnowledgeBase(question.trim())
      setState({ status: 'done', answer: result.answer, sources: result.sources, error: '' })
    } catch (error) {
      setState({ status: 'error', answer: '', sources: [], error: error.message })
    }
  }

  return (
    <div className="kb-ask">
      <form className="kb-ask__form" onSubmit={handleAsk}>
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the documents in the knowledge base…"
        />
        <button type="submit" className="documentation__link-btn" disabled={state.status === 'asking' || !question.trim()}>
          {state.status === 'asking' ? 'Searching…' : 'Ask'}
        </button>
      </form>
      {state.status === 'error' && <p className="documentation__hint documentation__hint--error">{state.error}</p>}
      {state.status === 'done' && (
        <div className="kb-ask__answer">
          <p>{state.answer}</p>
          {state.sources.length > 0 && (
            <details>
              <summary>Sources ({state.sources.length})</summary>
              <ol className="kb-ask__sources">
                {state.sources.map((source) => (
                  <li key={source.number}>
                    <strong>{source.doc_name}</strong>
                    <span>{source.text.length > 280 ? `${source.text.slice(0, 280)}…` : source.text}</span>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

// Two cards for one shared, portfolio-wide list (the same in every company's
// Documentation): files that were only uploaded (consult/download), and the
// knowledge base folder (files that were indexed, plus every generated report
// mirrored in automatically).
function KnowledgeBaseSections({ refreshKey, onChanged }) {
  const [documents, setDocuments] = useState([])
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    fetchDocuments()
      .then((rows) => {
        if (cancelled) return
        setDocuments(rows)
        setStatus('ready')
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  const uploaded = documents.filter((document) => !document.in_knowledge_base)
  const knowledgeBase = documents.filter((document) => document.in_knowledge_base)

  return (
    <>
      <section className="documentation__category">
        <h4>Uploaded Documents</h4>
        {status === 'loading' ? (
          <p className="documentation__hint">Loading…</p>
        ) : status === 'error' ? (
          <p className="documentation__hint documentation__hint--error">Could not load uploaded documents.</p>
        ) : uploaded.length === 0 ? (
          <p className="documentation__hint">
            Nothing uploaded yet — use Upload to add a document for people to consult.
          </p>
        ) : (
          uploaded.map((document) => <DocumentRow key={document.id} document={document} onChanged={onChanged} />)
        )}
      </section>

      <section className="documentation__category">
        <h4>Knowledge Base</h4>
        <p className="documentation__hint kb-section-note">
          One shared library for all companies. Documents you add (a business plan, for example) are the basis
          commercial profiles and competitiveness analyses are built on, and can answer questions. Every generated
          report is added automatically.
        </p>
        {status === 'ready' && knowledgeBase.length === 0 ? (
          <p className="documentation__hint">The knowledge base is empty.</p>
        ) : null}
        {status === 'ready' &&
          knowledgeBase.map((document) => <DocumentRow key={document.id} document={document} onChanged={onChanged} />)}
        {status === 'ready' && knowledgeBase.length > 0 && <AskKnowledgeBase />}
      </section>
    </>
  )
}

export default KnowledgeBaseSections
