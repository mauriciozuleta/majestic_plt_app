import { useCallback, useEffect, useRef, useState } from 'react'
import { runAssistantAction, sendChatMessage } from '../../services/chat'
import { cancelLocalReport, cancelTaxReport, fetchLocalModels, fetchLocalReport, fetchTaxReport, startLocalReport, startTaxReport } from '../../services/localModels'
import { fetchRagCountries } from '../../services/ragFiles'
import { useAppStore } from '../../store/useAppStore'

const POLL_MS = 700
const STORAGE_KEY = 'assistant:local-model'
// A message made through a local model carries this tag as its first "source"
// (the only extra field the chat log persists), so it still shows as one after
// a reload and is kept out of what Claude is sent as context.
export const LOCAL_TAG = 'Local model: '
export const isLocalMessage = (message) => Boolean(message.sources?.[0]?.startsWith(LOCAL_TAG))

const readStored = () => {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}
const writeStored = (value) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // not remembered across reloads — fine
  }
}

// A source entry that carries a built PDF's file name (the chat log keeps only text and sources).
export const PDF_PREFIX = 'PDF: '

// "tax cost of the very high opportunities" -> the opportunity category asked for, else null. A request
// about taxes/duties/tariffs/levies on opportunities is built as the tax-cost PDF (backend tax_report.py).
const RATINGS = [['very high', 'Very High'], ['not viable', 'Not Viable'], ['challenging', 'Challenging'], ['complex', 'Complex'], ['difficult', 'Difficult'], ['high', 'High']]
export function taxReportRating(request) {
  const text = request.toLowerCase()
  if (!/\b(tax|taxes|duty|duties|tariff|tariffs|levy|levies|vat|gct|customs)\b/.test(text) || !/opportunit/.test(text)) return null
  return RATINGS.find(([word]) => text.includes(word))?.[1] ?? 'Very High'
}

const REPORT_TIMEOUT_MS = 15 * 60 * 1000 // a report that takes longer is given up on, so the chat never stays locked
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Messages live in the global store, not local state — background-job
// completions (see services/backgroundJobs.js) are pushed here from
// wherever they finish, not just from this mounted component, so they need
// to land somewhere that survives navigation. The store also persists them
// server-side, so the log (and Claude's context) survives a reload.
//
// The assistant answers with Claude by default. Picking a local (Ollama)
// model switches the chat to building reports from one country's baked RAG
// files with that model — local models are used for nothing else.
export function useChatbox() {
  const messages = useAppStore((state) => state.assistantMessages)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [models, setModels] = useState({ available: false, models: [], detail: null })
  const [selectedModel, setSelectedModelState] = useState(() => readStored().model || '')
  const [reportCountry, setReportCountryState] = useState(() => readStored().country || '')
  const [reportCountries, setReportCountries] = useState([])
  const [live, setLive] = useState(null) // { text, statusText } while a local report is being written
  const jobRef = useRef(null)
  const kindRef = useRef('report') // 'report' | 'tax' — which kind of job jobRef holds
  const stopRef = useRef(false) // Stop pressed before the job id was known

  useEffect(() => {
    useAppStore.getState().loadAssistantMessages().catch(() => {})
  }, [])

  const refreshModels = useCallback((force = false) => {
    fetchLocalModels(force)
      .then(setModels)
      .catch((error) => setModels({ available: false, models: [], detail: error.message }))
    // countries that have a baked RAG file — the only ones a report can be built from
    fetchRagCountries()
      .then((data) => setReportCountries(data.countries.filter((item) => item.chunk_count > 0).map((item) => item.country)))
      .catch(() => setReportCountries([]))
  }, [])

  useEffect(() => {
    refreshModels()
  }, [refreshModels])

  const setSelectedModel = (name) => {
    setSelectedModelState(name)
    writeStored({ model: name, country: reportCountry })
  }
  const setReportCountry = (name) => {
    setReportCountryState(name)
    writeStored({ model: selectedModel, country: name })
  }

  const push = (message) => useAppStore.getState().appendAssistantMessage(message)

  const localMode = selectedModel !== '' && models.models.some((model) => model.name === selectedModel)
  // the chosen country if it still has a baked file, else the first one that does
  const country = reportCountries.includes(reportCountry) ? reportCountry : reportCountries[0] || ''

  const sendLocalReport = async (request) => {
    const tag = `${LOCAL_TAG}${selectedModel} · ${country}`
    push({ sender: 'user', text: request, sources: [tag] })
    setDraft('')
    setSending(true)
    setLive({ text: '', statusText: 'Starting…' })
    stopRef.current = false
    const deadline = Date.now() + REPORT_TIMEOUT_MS
    try {
      const taxRating = taxReportRating(request)
      if (taxRating) {
        kindRef.current = 'tax'
        let taxJob = await startTaxReport({ model: selectedModel, country, rating: taxRating })
        jobRef.current = taxJob.id
        if (stopRef.current) cancelTaxReport(taxJob.id).catch(() => {})
        while (taxJob.status === 'running') {
          if (Date.now() > deadline + 45 * 60 * 1000) {
            cancelTaxReport(taxJob.id).catch(() => {})
            throw new Error('The tax report took too long and was stopped.')
          }
          const left = taxJob.eta_seconds != null && taxJob.total > 0 && taxJob.done < taxJob.total ? ` · about ${taxJob.eta_seconds < 90 ? `${Math.max(1, taxJob.eta_seconds)} s` : `${Math.round(taxJob.eta_seconds / 60)} min`} left` : ''
          setLive({ text: '', statusText: `${taxJob.status_text}${left}` })
          await sleep(1500)
          taxJob = await fetchTaxReport(taxJob.id)
        }
        const found = taxJob.rows.filter((row) => row.total_pct != null).length
        if (taxJob.status === 'done') {
          push({
            sender: 'bot',
            text: `${taxJob.summary}\n\nThe PDF has all ${taxJob.rows.length} products (${found} with tax rates found in ${country}'s documents).`,
            sources: [tag, `${PDF_PREFIX}${taxJob.file}`],
          })
        } else if (taxJob.status === 'cancelled') push({ sender: 'bot', text: 'Stopped.', sources: [tag] })
        else push({ sender: 'bot', text: taxJob.error || 'The tax report could not be built.', sources: [tag] })
        return
      }
      kindRef.current = 'report'
      let job = await startLocalReport({ model: selectedModel, country, request })
      jobRef.current = job.id
      if (stopRef.current) cancelLocalReport(job.id).catch(() => {})
      while (job.status === 'running') {
        if (Date.now() > deadline) {
          cancelLocalReport(job.id).catch(() => {})
          throw new Error('The local model took too long, so the report was stopped. Try a smaller model or a shorter request.')
        }
        setLive({ text: job.text, statusText: job.status_text })
        await sleep(POLL_MS)
        job = await fetchLocalReport(job.id)
      }
      // "<file>: [1] Taxes, [2] Sanitary …" — the last part of each section's heading path, grouped by file
      const byDocument = new Map()
      job.sources.forEach((source) => {
        const heading = (source.section || 'section').split(' > ').pop()
        byDocument.set(source.document, [...(byDocument.get(source.document) || []), `[${source.number}] ${heading}`])
      })
      const documents = [...byDocument].map(([document, items]) => `${document}: ${items.join(', ')}`)
      // an import-tax question is answered from the destination country's documents, which may not be the selected one
      const doneTag = job.country && job.country !== country ? `${LOCAL_TAG}${selectedModel} · ${job.country}` : tag
      if (job.status === 'done') push({ sender: 'bot', text: job.text, sources: [doneTag, ...documents] })
      else if (job.status === 'cancelled') push({ sender: 'bot', text: job.text ? `${job.text}\n\n(Stopped.)` : 'Stopped.', sources: [tag] })
      else push({ sender: 'bot', text: job.error || 'The report could not be built.', sources: [tag] })
    } catch (error) {
      push({ sender: 'bot', text: error.message, sources: [tag] })
    } finally {
      jobRef.current = null
      setLive(null)
      setSending(false)
    }
  }

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed || sending) return

    if (localMode) {
      if (!country) return
      await sendLocalReport(trimmed)
      return
    }

    push({ sender: 'user', text: trimmed })
    const history = useAppStore.getState().assistantMessages.filter((message) => !isLocalMessage(message))
    setDraft('')
    setSending(true)

    try {
      const { reply, sources, actions } = await sendChatMessage(history)
      push({ sender: 'bot', text: reply, sources })
      actions.forEach((action) => {
        // Failures are reported into the chat by runBackgroundJob itself,
        // except a failure to even start one.
        runAssistantAction(action).catch((error) => push({ sender: 'bot', text: `Could not finish that: ${error.message}` }))
      })
    } catch (error) {
      push({ sender: 'bot', text: error.message })
    } finally {
      setSending(false)
    }
  }

  const stopLocalReport = () => {
    stopRef.current = true
    if (jobRef.current) (kindRef.current === 'tax' ? cancelTaxReport : cancelLocalReport)(jobRef.current).catch(() => {})
  }

  return {
    messages,
    draft,
    setDraft,
    handleSend,
    sending,
    models,
    refreshModels,
    selectedModel: localMode ? selectedModel : '',
    setSelectedModel,
    localMode,
    reportCountries,
    country,
    setReportCountry,
    live,
    stopLocalReport,
  }
}
