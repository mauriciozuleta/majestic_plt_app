import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { calculateDianTaxes, fetchDianJob, startDianLookup } from '../../services/dianTax'
import { fromDianCalculation } from './taxResult'

const POLL_MS = 1500
const DEBOUNCE_MS = 600
const VALID_CODE = /^(\d{4}|\d{6}|\d{8}|\d{10})$/

const digitsOf = (text) => (text || '').replace(/[\s.\-]/g, '')

// The Colombia (DIAN) side of the Tax Calculator: for the selected product's HS code it runs a lookup (a background job that is polled), keeps the
// choices DIAN can ask for (which tariff line when the code covers several; which row when it lists several valid Gravamen / IVA rows) and,
// once the rates are known, calculates the taxes of 1 kg at `price` USD. `onResult` receives the normalized per-kg result (or null while it can't
// be calculated). Lookups of a product the user clicked past are ignored.
export function useDianFlow({ enabled, hsCode, savedLine, price, onLineChosen, onResult }) {
  const [status, setStatus] = useState('idle') // idle | running | done
  const [progress, setProgress] = useState([])
  const [lookup, setLookup] = useState(null)
  const [error, setError] = useState('')
  const [chosen, setChosen] = useState({ gravamen: null, iva: null })
  const [typedCode, setTypedCode] = useState('') // when the product has no HS code, or the user wants another one
  const runId = useRef(0)
  const timer = useRef(null)
  const poller = useRef(null)
  const lastCalc = useRef('')
  const onResultRef = useRef(onResult)
  onResultRef.current = onResult

  const code = digitsOf(typedCode || savedLine || hsCode)

  // another product: its own code, not the one typed or picked for the previous one
  useEffect(() => {
    setTypedCode('')
  }, [hsCode])

  const stop = useCallback(() => {
    runId.current += 1
    window.clearTimeout(timer.current)
    window.clearTimeout(poller.current)
  }, [])

  const run = useCallback(
    async (target, forceRefresh = false) => {
      const id = ++runId.current
      window.clearTimeout(poller.current)
      setStatus('running')
      setError('')
      setLookup(null)
      setProgress([])
      setChosen({ gravamen: null, iva: null })
      lastCalc.current = ''
      try {
        const { jobId } = await startDianLookup({ hsCode: target, forceRefresh })
        const poll = () => {
          poller.current = window.setTimeout(async () => {
            if (id !== runId.current) return
            try {
              const job = await fetchDianJob(jobId)
              if (id !== runId.current) return
              setProgress(job.progress || [])
              if (job.status === 'done') {
                setLookup(job.result)
                setStatus('done')
                return
              }
              poll()
            } catch (err) {
              if (id !== runId.current) return
              setError(err.message)
              setStatus('done')
            }
          }, POLL_MS)
        }
        poll()
      } catch (err) {
        if (id !== runId.current) return
        setError(err.message)
        setStatus('done')
      }
    },
    [],
  )

  // a product (or its code) chosen: look it up, after a short pause so clicking through the list doesn't fire a lookup per click
  useEffect(() => {
    window.clearTimeout(timer.current)
    if (!enabled) {
      stop()
      setStatus('idle')
      setLookup(null)
      setError('')
      return undefined
    }
    if (!VALID_CODE.test(code)) {
      stop()
      setStatus('idle')
      setLookup(null)
      setError('')
      onResultRef.current(null)
      return undefined
    }
    onResultRef.current(null)
    timer.current = window.setTimeout(() => run(code), DEBOUNCE_MS)
    return () => window.clearTimeout(timer.current)
  }, [enabled, code, run, stop])

  useEffect(() => () => stop(), [stop])

  const ok = lookup?.status === 'ok' ? lookup : null
  // the Gravamen / IVA the calculation uses: the only valid row, or the one the user picked among several
  const effective = useMemo(() => {
    if (!ok) return { gravamen: null, iva: null, waiting: false }
    const need = (tax) => ok.needsInput.find((item) => item.tax === tax)
    const gravamen = need('gravamen') ? (chosen.gravamen != null ? ok.gravamenRows[chosen.gravamen] : null) : ok.gravamen
    const iva = need('iva') ? (chosen.iva != null ? ok.ivaRows[chosen.iva] : null) : ok.iva
    const waiting = Boolean((need('gravamen') && chosen.gravamen == null) || (need('iva') && chosen.iva == null))
    return { gravamen, iva, waiting }
  }, [ok, chosen])

  // the taxes of 1 kg
  useEffect(() => {
    if (!enabled) return undefined
    if (!ok || effective.waiting || !(price > 0)) {
      onResultRef.current(null)
      return undefined
    }
    const key = JSON.stringify([ok.query.resolvedHsCode, ok.source.retrievedAt, effective.gravamen, effective.iva, price])
    if (key === lastCalc.current) return undefined
    let cancelled = false
    calculateDianTaxes({ customsValue: price, gravamen: effective.gravamen, iva: effective.iva, ivaStatus: ok.ivaStatus })
      .then((calc) => {
        if (cancelled) return
        lastCalc.current = key
        onResultRef.current(fromDianCalculation(price, ok, calc))
      })
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [enabled, ok, effective, price])

  return {
    status,
    progress,
    lookup,
    error,
    code,
    chosen,
    effective,
    typedCode,
    setTypedCode,
    choose: (tax, index) => setChosen((prev) => ({ ...prev, [tax]: index })),
    // the code covers several tariff lines: the user picked one
    selectLine: (hs) => {
      onLineChosen?.(hs)
      setTypedCode(hs)
    },
    refresh: () => run(code, true),
  }
}
