// Shared price-formatting helpers for the Market Analysis product tables
// (Colombia and USA). Always comma-for-thousands, period-for-decimals
// (en-US grouping) regardless of the currency involved, so every number
// shown anywhere in the app is safe to re-parse for math later — never
// locale-dependent (es-CO would flip the separators).

export function formatUsd(value) {
  if (value === null || value === undefined) return null
  return `US$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatLocalCurrency(value, currencyCode) {
  if (value === null || value === undefined) return null
  return `${currencyCode}$${Math.round(value).toLocaleString('en-US')}`
}

// The on-screen "side by side" price format: the USD figure first, with
// the original local-currency amount alongside for traceability. Falls
// back to the local amount alone when no exchange rate is available yet,
// and to '—' when there's no price at all.
export function formatPriceLine(usdValue, localValue, currencyCode) {
  const usd = formatUsd(usdValue)
  if (usd !== null) {
    const local = currencyCode ? formatLocalCurrency(localValue, currencyCode) : null
    return local ? `${usd} (${local})` : usd
  }
  if (currencyCode) {
    const local = formatLocalCurrency(localValue, currencyCode)
    if (local !== null) return local
  }
  return '—'
}
