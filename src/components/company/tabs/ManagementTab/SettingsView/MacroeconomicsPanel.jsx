import { useEffect, useState } from 'react'
import { fetchCountryInflation, updateCountryInflation } from '../../../../../services/settings'
import './MacroeconomicsPanel.css'

// Applies to every company whose OWN home country matches this pill's
// country (Company.country_code) — not just the one company whose
// commercial-structure row this pill happens to render under. A position
// elsewhere, or in a company located in a different country, keeps
// whatever salary it already has for Year 2+. Wired to every country (not
// just United States) since the same inflation-driven Year 2+ recalculation
// applies everywhere, keyed by country_code (CountryInflation) in the DB.
function MacroeconomicsPanel({ countryCode }) {
  const [savedRate, setSavedRate] = useState(0)
  const [draftRate, setDraftRate] = useState('0')
  const [status, setStatus] = useState('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!countryCode) return undefined
    let cancelled = false
    setStatus('loading')
    fetchCountryInflation(countryCode)
      .then((settings) => {
        if (cancelled) return
        const rate = Number(settings.inflation_pct ?? 0)
        setSavedRate(rate)
        setDraftRate(String(rate))
        setStatus('idle')
      })
      .catch((error) => {
        if (!cancelled) {
          setStatus('error')
          setMessage(error.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [countryCode])

  const parsedDraft = Number(draftRate)
  const isDirty = Number.isFinite(parsedDraft) && parsedDraft !== savedRate

  const handleSave = async () => {
    if (!Number.isFinite(parsedDraft) || !countryCode) return
    setStatus('saving')
    setMessage('')
    try {
      const result = await updateCountryInflation(countryCode, parsedDraft)
      setSavedRate(parsedDraft)
      setMessage(
        result.positions_updated > 0
          ? `Saved — recalculated Year 2 onward for ${result.positions_updated} position${result.positions_updated === 1 ? '' : 's'} in companies located here.`
          : 'Saved.',
      )
      setStatus('idle')
    } catch (error) {
      setStatus('error')
      setMessage(error.message || 'Failed to save inflation rate.')
    }
  }

  return (
    <div className="macro-panel">
      <p className="macro-panel__hint">
        Applied every year starting in Year 2, compounding on the previous year's cost — Year 2 = Year 1 × (1 + rate), Year 3 = Year 2 ×
        (1 + rate), and so on. Applies to every company actually located in this country, not just one.
      </p>
      <label className="macro-panel__input-row">
        Inflation (annual %)
        <input
          type="number"
          step="0.1"
          value={draftRate}
          onChange={(event) => setDraftRate(event.target.value)}
          disabled={status === 'loading' || status === 'saving'}
        />
        <button type="button" className="macro-panel__save-btn" onClick={handleSave} disabled={!isDirty || status === 'saving'}>
          {status === 'saving' ? 'Saving…' : 'Save'}
        </button>
      </label>
      {message && <p className={`macro-panel__message ${status === 'error' ? 'is-error' : ''}`}>{message}</p>}
    </div>
  )
}

export default MacroeconomicsPanel
