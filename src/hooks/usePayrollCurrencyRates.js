import { useEffect, useState } from 'react'
import { fetchSettings } from '../services/settings'
import { fetchExchangeRate } from '../services/exchangeRate'
import { COP_PER_USD_FALLBACK } from '../services/colombiaPayrollTax'
import { ANG_PER_USD_FALLBACK } from '../services/stMaartenPayrollTax'

// Shared by every Payroll-tab table/view that shows a local-currency
// subtitle under a USD value. Colombia uses the same locked "projected"
// rate as its Settings panel (so figures agree everywhere it's shown,
// rather than drifting off a live quote); Sint Maarten has no locked-rate
// concept, so it uses the live rate.
export function usePayrollCurrencyRates() {
  const [copPerUsd, setCopPerUsd] = useState(COP_PER_USD_FALLBACK)
  const [angPerUsd, setAngPerUsd] = useState(ANG_PER_USD_FALLBACK)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (!cancelled && settings.colombia_projected_cop_per_usd) setCopPerUsd(settings.colombia_projected_cop_per_usd)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchExchangeRate('ANG', 'USD')
      .then((result) => {
        if (!cancelled && result?.rate > 0) setAngPerUsd(1 / result.rate)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  return { copPerUsd, angPerUsd }
}
