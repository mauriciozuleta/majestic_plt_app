import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  addRagFile,
  bakeAllPending,
  bakeRagFiles,
  cancelRagJob,
  deleteRagFile,
  fetchRagCountries,
  fetchRagCountry,
  fetchRagDocument,
  fetchRagQueue,
  loadRagFiles,
} from '../../services/ragFiles'
import { addPortfolioAndOpportunityFiles } from '../../services/ragDataFiles'
import './RagFilesView.css'

const POLL_MS = 1000
const ACCEPT = '.pdf,.docx,.xlsx,.xlsm,.xls,.csv,.tsv,.md,.markdown,.txt'
const STATUS_LABELS = { uploaded: 'Uploaded', loaded: 'Loaded (JSON)', baked: 'Baked', error: 'Error' }
const FORMAT_LABELS = { pdf: 'PDF', docx: 'Word', xlsx: 'Excel', xlsm: 'Excel', xls: 'Excel', csv: 'CSV', tsv: 'CSV', md: 'Markdown', markdown: 'Markdown', txt: 'Text' }

function formatSize(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const formatWhen = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')

// Sections of one loaded file's JSON, fetched when its row is opened.
function DocumentSections({ country, filename }) {
  const [document, setDocument] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    fetchRagDocument(country, filename)
      .then((data) => !cancelled && setDocument(data))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [country, filename])
  if (error) return <p className="rag-files__error">{error}</p>
  if (!document) return <p className="rag-files__hint">Loading…</p>
  return (
    <div className="rag-files__sections">
      <p className="rag-files__hint">
        “{document.title}” · {document.stats.sections} section{document.stats.sections === 1 ? '' : 's'} · {document.stats.characters.toLocaleString('en-US')} characters
      </p>
      {document.warnings.length > 0 && <p className="rag-files__warn">{document.warnings.join(' ')}</p>}
      <ol>
        {document.sections.map((section) => (
          <li key={section.id}>
            <strong>{section.path}</strong>
            <span>{section.content.replace(/\s+/g, ' ').slice(0, 140)}{section.content.length > 140 ? '…' : ''}</span>
            <em>{section.content.length.toLocaleString('en-US')} chars</em>
          </li>
        ))}
      </ol>
    </div>
  )
}

function RagFilesView() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [countries, setCountries] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [detail, setDetail] = useState(null)
  const [uploadCountry, setUploadCountry] = useState('')
  const [uploading, setUploading] = useState(null) // { done, total, name }
  const [messages, setMessages] = useState([])
  const [openFile, setOpenFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [building, setBuilding] = useState('') // progress text while the portfolio/opportunity files are built
  const [queue, setQueue] = useState({ active: [], recent: [] })
  const fileInputRef = useRef(null)

  const active = useMemo(() => {
    const wanted = searchParams.get('country')
    return countries.find((item) => item.country === wanted)?.country ?? countries[0]?.country ?? ''
  }, [countries, searchParams])

  const selectTab = useCallback(
    (name) => {
      setSearchParams({ country: name }, { replace: true })
      setUploadCountry(name)
      setOpenFile(null)
      setMessages([])
    },
    [setSearchParams],
  )

  const refreshCountries = useCallback(
    () =>
      fetchRagCountries()
        .then((data) => {
          setCountries(data.countries)
          setStatus('ready')
        })
        .catch((err) => {
          setError(err.message)
          setStatus('error')
        }),
    [],
  )

  const refreshDetail = useCallback(
    (name) =>
      fetchRagCountry(name)
        .then((data) => {
          setDetail(data)
          return data
        })
        .catch((err) => setError(err.message)),
    [],
  )

  useEffect(() => {
    refreshCountries()
  }, [refreshCountries])

  // The country's files; while another country's detail is still showing, nothing is rendered.
  useEffect(() => {
    if (active) refreshDetail(active)
  }, [active, refreshDetail])

  const refreshQueue = useCallback(() => fetchRagQueue().then(setQueue).catch(() => {}), [])

  useEffect(() => {
    refreshQueue()
  }, [refreshQueue])

  // While anything is queued or running: follow the queue, and refresh the counts when a job ends.
  const busyJobs = queue.active.length
  const runningId = queue.active.find((job) => job.status === 'running')?.id ?? ''
  useEffect(() => {
    if (busyJobs === 0 || !active) return undefined
    const timer = setInterval(async () => {
      await refreshQueue()
      refreshDetail(active)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [busyJobs, active, refreshQueue, refreshDetail])

  // a job finished or the next one started: counts and statuses may have changed
  useEffect(() => {
    refreshCountries()
    if (active) refreshDetail(active)
  }, [runningId, busyJobs, active, refreshCountries, refreshDetail])

  const uploadFiles = async (name, fileList) => {
    const files = [...fileList]
    if (!name || files.length === 0) return
    setError('')
    const results = []
    for (const [index, file] of files.entries()) {
      setUploading({ done: index, total: files.length, name: file.name })
      try {
        await addRagFile(name, file)
        results.push({ tone: 'ok', text: `${file.name} added.` })
      } catch (err) {
        results.push({ tone: 'error', text: `${file.name}: ${err.message}` })
      }
    }
    setUploading(null)
    setMessages(results)
    await refreshCountries()
    if (name === active) await refreshDetail(name)
    else selectTab(name)
  }

  const onPick = (event) => {
    // copied first: resetting the input below empties its live FileList
    const files = [...event.target.files]
    const name = uploadCountry || active
    event.target.value = ''
    uploadFiles(name, files)
  }

  const run = async (action) => {
    setError('')
    setMessages([])
    try {
      setDetail(await action(active))
      refreshCountries()
      refreshQueue()
    } catch (err) {
      setError(err.message)
    }
  }

  const addDataFiles = async () => {
    setError('')
    setMessages([])
    setBuilding('Starting…')
    try {
      const results = await addPortfolioAndOpportunityFiles(
        countries.map((item) => item.country),
        setBuilding,
      )
      setMessages(
        results.length === 0
          ? [{ tone: 'error', text: 'No portfolio or opportunity data found to add.' }]
          : results.map((result) => ({
              tone: result.ok ? 'ok' : 'error',
              text: result.ok ? `${result.country}: ${result.file} added.` : `${result.country}: ${result.file} — ${result.error}`,
            })),
      )
      await refreshCountries()
      if (active) await refreshDetail(active)
    } catch (err) {
      setError(err.message)
    } finally {
      setBuilding('')
    }
  }

  const cancelJob = async (id) => {
    try {
      await cancelRagJob(id)
    } catch (err) {
      setError(err.message)
    }
    refreshQueue()
  }

  const runBakeAll = async () => {
    setError('')
    try {
      const data = await bakeAllPending()
      setQueue({ active: data.active, recent: data.recent })
    } catch (err) {
      setError(err.message)
    }
  }

  const removeFile = async (file) => {
    if (!window.confirm(`Remove ${file.name} (and its JSON) from ${active}?`)) return
    setError('')
    try {
      setDetail(await deleteRagFile(active, file.name))
      setOpenFile(null)
      refreshCountries()
    } catch (err) {
      setError(err.message)
    }
  }

  if (status === 'loading') return <div className="panel-surface rag-files"><p className="rag-files__hint">Loading…</p></div>

  const files = detail?.file_list ?? []
  const toLoad = (detail?.uploaded ?? 0) + (detail?.error ?? 0)
  const job = detail?.job
  const myJobs = queue.active.filter((item) => item.country === active)
  const loadJob = myJobs.find((item) => item.kind === 'load')
  const bakeJob = myJobs.find((item) => item.kind === 'bake')
  const running = job?.status === 'running'
  const busy = uploading != null
  const hasJob = myJobs.length > 0
  const pendingCountries = countries.filter(
    (item) => item.needs_bake && !queue.active.some((queued) => queued.country === item.country && queued.kind === 'bake'),
  )

  return (
    <div className="panel-surface rag-files">
      <header className="rag-files__header">
        <h3>RAG Files</h3>
        <p>
          Documents for each country. Add files, <strong>Load</strong> them to convert each one to JSON, then <strong>Bake</strong> the
          country to add them to its RAG file.
        </p>
      </header>

      {status === 'error' && <p className="rag-files__error">{error}</p>}

      {countries.length === 0 && status === 'ready' && (
        <p className="rag-files__hint">No countries yet — add a country in Commercial Structure first.</p>
      )}

      {countries.length > 0 && (
        <>
          <div className="rag-files__toolbar">
            <label>
              Country
              <select value={uploadCountry || active} onChange={(event) => setUploadCountry(event.target.value)} disabled={busy}>
                {countries.map((item) => (
                  <option key={item.country} value={item.country}>
                    {item.country}
                  </option>
                ))}
              </select>
            </label>
            <input ref={fileInputRef} type="file" multiple accept={ACCEPT} style={{ display: 'none' }} onChange={onPick} />
            <button type="button" className="rag-files__btn rag-files__btn--primary" onClick={() => fileInputRef.current?.click()} disabled={busy}>
              + Add file
            </button>
            <button
              type="button"
              className="rag-files__btn"
              onClick={addDataFiles}
              disabled={busy || Boolean(building)}
              title="Add each country's product portfolio and product opportunities as files (then Load and Bake them)"
            >
              {building ? 'Building…' : '+ Portfolios & opportunities'}
            </button>
            <button
              type="button"
              className="rag-files__btn rag-files__btn--bake is-pending"
              onClick={runBakeAll}
              disabled={pendingCountries.length === 0}
              title="Queue a Bake for every country that has loaded documents not baked yet"
            >
              Bake all{pendingCountries.length ? ` (${pendingCountries.length})` : ''}
            </button>
            <span className="rag-files__hint">PDF, Word (.docx), Excel, CSV, Markdown or text · up to 50 MB each</span>
          </div>

          {building && <p className="rag-files__progress">{building}</p>}

          {queue.active.length > 0 && (
            <div className="rag-files__queue" aria-label="Job queue">
              {queue.active.map((item) => (
                <div key={item.id} className={`rag-files__queue-item ${item.status === 'running' ? 'is-running' : ''}`}>
                  <div>
                    <strong>
                      {item.status === 'running' ? 'Running' : `#${item.position} in line`} · {item.kind === 'load' ? 'Load' : 'Bake'} {item.country}
                    </strong>
                    <span>{item.message}</span>
                    {item.status === 'running' && item.total > 0 && <progress value={item.done} max={item.total} aria-label="progress" />}
                  </div>
                  <button type="button" className="rag-files__queue-cancel" onClick={() => cancelJob(item.id)} aria-label={`Cancel ${item.kind} ${item.country}`}>
                    Cancel
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="rag-files__tab-bar" role="tablist">
            {countries.map((item) => (
              <button
                key={item.country}
                type="button"
                role="tab"
                aria-selected={item.country === active}
                className={`rag-files__tab ${item.country === active ? 'is-active' : ''}`}
                onClick={() => selectTab(item.country)}
                title={item.needs_bake ? 'Has documents that are not baked yet' : undefined}
              >
                {item.country}
                {item.files > 0 && <span className="rag-files__tab-count">{item.files}</span>}
                {item.needs_bake && <span className="rag-files__tab-dot" aria-label="needs bake" />}
                {queue.active.some((queued) => queued.country === item.country) && <span className="rag-files__tab-busy" aria-label="queued or running" />}
              </button>
            ))}
          </div>

          {detail && detail.country === active && (
            <section
              className={`rag-files__card ${dragging ? 'is-dragging' : ''}`}
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                uploadFiles(active, event.dataTransfer.files)
              }}
            >
              <div className="rag-files__card-head">
                <div>
                  <h4>{detail.country}</h4>
                  <p className="rag-files__hint">
                    {detail.files} file{detail.files === 1 ? '' : 's'} · {detail.loaded + detail.baked} loaded · {detail.baked} baked
                    {detail.baked_at && ` · RAG file updated ${formatWhen(detail.baked_at)} (${detail.chunk_count.toLocaleString('en-US')} chunks${detail.embedded ? ', embedded' : ', keyword search only'})`}
                  </p>
                </div>
                <div className="rag-files__actions">
                  <button type="button" className="rag-files__btn rag-files__btn--load" onClick={() => run(loadRagFiles)} disabled={busy || Boolean(loadJob) || toLoad === 0}>
                    {loadJob ? (loadJob.status === 'running' ? 'Loading…' : 'Load queued') : `Load${toLoad ? ` (${toLoad})` : ''}`}
                  </button>
                  <button
                    type="button"
                    className={`rag-files__btn rag-files__btn--bake ${detail.needs_bake ? 'is-pending' : ''}`}
                    onClick={() => run(bakeRagFiles)}
                    disabled={busy || Boolean(bakeJob) || !detail.needs_bake}
                    title={detail.needs_bake ? 'Queue adding the loaded documents to the country’s RAG file' : 'Everything loaded is already baked'}
                  >
                    {bakeJob ? (bakeJob.status === 'running' ? 'Baking…' : 'Bake queued') : detail.needs_bake ? 'Bake' : 'Baked ✓'}
                  </button>
                </div>
              </div>

              {uploading && (
                <p className="rag-files__progress">
                  Adding {uploading.name} ({uploading.done + 1} of {uploading.total})…
                </p>
              )}
              {job && !hasJob && job.finished_at && (
                <div className={`rag-files__job ${job.status === 'failed' ? 'is-failed' : ''}`}>
                  <span>
                    {job.kind === 'load' ? 'Load' : 'Bake'}: {job.message}
                  </span>
                </div>
              )}
              {error && <p className="rag-files__error">{error}</p>}
              {messages.map((message, index) => (
                <p key={`${index}-${message.text}`} className={message.tone === 'error' ? 'rag-files__error' : 'rag-files__ok'}>
                  {message.text}
                </p>
              ))}

              {files.length === 0 ? (
                <div className="rag-files__empty">
                  <p>No files for {detail.country} yet.</p>
                  <p className="rag-files__hint">Drag files here, or use + Add file.</p>
                </div>
              ) : (
                <table className="rag-files__table">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Type</th>
                      <th className="is-num">Size</th>
                      <th>Status</th>
                      <th className="is-num">Sections</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {files.map((file) => {
                      const opened = openFile === file.name
                      return (
                        <FileRow
                          key={file.name}
                          file={file}
                          country={detail.country}
                          opened={opened}
                          onToggle={() => setOpenFile(opened ? null : file.name)}
                          onRemove={() => removeFile(file)}
                          disabled={busy || hasJob}
                        />
                      )
                    })}
                  </tbody>
                </table>
              )}
              <p className="rag-files__hint rag-files__folder">
                Folder: <code>backend/documents/rag_files/{detail.country}/</code> — files in <code>source</code>, converted JSON in <code>json</code>,
                the RAG file as <code>{detail.country}.rag.json</code>.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function FileRow({ file, country, opened, onToggle, onRemove, disabled }) {
  const canOpen = file.status === 'loaded' || file.status === 'baked'
  return (
    <>
      <tr className={`rag-files__row ${opened ? 'is-open' : ''}`}>
        <td className="rag-files__name" title={file.name}>
          {canOpen ? (
            <button type="button" className="rag-files__link" onClick={onToggle} aria-expanded={opened}>
              {opened ? '▾' : '▸'} {file.name}
            </button>
          ) : (
            file.name
          )}
        </td>
        <td>{FORMAT_LABELS[file.format] ?? file.format.toUpperCase()}</td>
        <td className="is-num">{formatSize(file.size_bytes)}</td>
        <td>
          <span className={`rag-files__chip rag-files__chip--${file.status}`}>{STATUS_LABELS[file.status]}</span>
        </td>
        <td className="is-num">{file.sections ?? '—'}</td>
        <td className="is-num">
          <button type="button" className="rag-files__remove" onClick={onRemove} disabled={disabled} aria-label={`Remove ${file.name}`} title="Remove">
            ×
          </button>
        </td>
      </tr>
      {file.status === 'error' && (
        <tr className="rag-files__detail-row">
          <td colSpan={6}>
            <p className="rag-files__error">{file.error}</p>
          </td>
        </tr>
      )}
      {opened && canOpen && (
        <tr className="rag-files__detail-row">
          <td colSpan={6}>
            <DocumentSections country={country} filename={file.name} />
          </td>
        </tr>
      )}
    </>
  )
}

export default RagFilesView
