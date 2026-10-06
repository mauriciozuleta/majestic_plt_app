import { useEffect, useRef, useState } from 'react'
import './Chatbox.css'
import { IconPlayerStop, IconSend } from '@tabler/icons-react'
import { LOCAL_TAG, PDF_PREFIX, isLocalMessage, useChatbox } from './useChatbox'
import { reportFileUrl } from '../../services/localModels'
import ReportModal from './ReportModal'

function Chatbox() {
  const {
    messages,
    draft,
    setDraft,
    handleSend,
    sending,
    models,
    refreshModels,
    selectedModel,
    setSelectedModel,
    localMode,
    reportCountries,
    country,
    setReportCountry,
    live,
    stopLocalReport,
  } = useChatbox()
  const endRef = useRef(null)
  // the report shown in the larger window: { text, model, country, request, sources }
  const [openReport, setOpenReport] = useState(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, sending, live?.text])

  const noCountry = localMode && reportCountries.length === 0
  const placeholder = localMode
    ? country
      ? `Describe the report to build from ${country}'s RAG files…`
      : 'No country has baked RAG files yet'
    : 'Ask about your documents…'

  return (
    <div className="chatbox">
      <div className="chatbox__header">Assistant</div>

      <div className="chatbox__models">
        <select
          value={selectedModel}
          onChange={(event) => setSelectedModel(event.target.value)}
          onFocus={() => refreshModels(true)}
          disabled={sending}
          aria-label="Model"
          title="Claude answers questions. A local model (Ollama) only builds reports from a country's RAG files."
        >
          <option value="">Claude — assistant</option>
          {models.available && models.models.length > 0 && (
            <optgroup label="Local · reports from RAG files">
              {models.models.map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name}
                  {model.parameter_size ? ` (${model.parameter_size})` : ''}
                </option>
              ))}
            </optgroup>
          )}
          {!models.available && (
            <option disabled value="__unavailable" title={models.detail || ''}>
              Local models: Ollama not running
            </option>
          )}
          {models.available && models.models.length === 0 && (
            <option disabled value="__none">
              Local models: none installed
            </option>
          )}
        </select>
        {localMode && (
          <select
            value={country}
            onChange={(event) => setReportCountry(event.target.value)}
            disabled={sending || reportCountries.length === 0}
            aria-label="Country for the report"
          >
            {reportCountries.length === 0 && <option value="">No baked countries</option>}
            {reportCountries.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
      </div>
      {localMode && (
        <div className="chatbox__hint">
          {noCountry
            ? 'Load and Bake a country’s documents in RAG Files first.'
            : 'This model only writes reports from the selected country’s baked documents.'}
        </div>
      )}

      <div className={`chatbox__messages ${localMode ? 'chatbox__messages--local' : ''}`}>
        {messages.length === 0 ? (
          <div className="chatbox__message chatbox__message--bot">No messages yet.</div>
        ) : (
          messages.map((message, index) => {
            const local = isLocalMessage(message)
            const tag = local ? message.sources[0].slice(LOCAL_TAG.length) : null
            const pdfFile = local ? message.sources.find((source) => source.startsWith(PDF_PREFIX))?.slice(PDF_PREFIX.length) : null
            const sources = (local ? message.sources.slice(1) : message.sources).filter((source) => !source.startsWith(PDF_PREFIX))
            // a finished report (not an error or a stop notice) can be opened, copied and saved
            const [reportModel, reportCountry] = tag ? tag.split(' · ') : []
            const canOpen = local && message.sender === 'bot' && sources.length > 0 && !pdfFile
            return (
              <div key={message.id} className={`chatbox__message chatbox__message--${message.sender} ${local && message.sender === 'bot' ? 'chatbox__message--report' : ''}`}>
                {message.text}
                {tag && <div className="chatbox__sources">Local model · {tag}</div>}
                {pdfFile && (
                  <a className="chatbox__open-report" href={reportFileUrl(reportCountry, pdfFile)} target="_blank" rel="noreferrer">
                    Open PDF
                  </a>
                )}
                {canOpen && (
                  <button
                    type="button"
                    className="chatbox__open-report"
                    onClick={() => setOpenReport({ text: message.text, model: reportModel, country: reportCountry, request: messages[index - 1]?.text ?? '', sources })}
                  >
                    Open report
                  </button>
                )}
                {sources?.length > 0 && <div className="chatbox__sources">From: {sources.join(' · ')}</div>}
              </div>
            )
          })
        )}
        {live && (
          <div className="chatbox__message chatbox__message--bot chatbox__message--report">
            {live.text || live.statusText}
            {live.text && <div className="chatbox__sources">Writing…</div>}
          </div>
        )}
        {sending && !live && <div className="chatbox__message chatbox__message--bot">Thinking…</div>}
        <div ref={endRef} />
      </div>
      {openReport && <ReportModal report={openReport} onClose={() => setOpenReport(null)} />}
      <div className="chatbox__composer">
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              handleSend()
            }
          }}
          placeholder={placeholder}
          disabled={sending || (localMode && !country)}
        />
        {sending && localMode ? (
          <button type="button" onClick={stopLocalReport} aria-label="Stop the report" title="Stop">
            <IconPlayerStop size={14} stroke={1.8} />
          </button>
        ) : (
          <button type="button" onClick={handleSend} disabled={sending || (localMode && !country)} aria-label="Send message">
            <IconSend size={14} stroke={1.8} />
          </button>
        )}
      </div>
    </div>
  )
}

export default Chatbox
