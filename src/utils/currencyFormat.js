// Consistent currency formatting for the whole app:
// - Currency code before the "$" (e.g. "USD $1,234.56", "COP $1,750,905.00")
// - Always "," for thousands and "." for decimals — the 'en-US' locale is
//   passed explicitly so this never silently changes with the viewer's
//   browser locale.
// - Countries whose local currency isn't USD (Colombia/COP, Sint Maarten/
//   ANG, etc.) show both the local-currency amount and its USD equivalent,
//   via formatDualCurrency.

export function formatCurrencyValue(value, currencyCode = 'USD', options = {}) {
  const { minimumFractionDigits = 2, maximumFractionDigits = 2 } = options
  const number = Number(value) || 0
  const formatted = number.toLocaleString('en-US', { minimumFractionDigits, maximumFractionDigits })
  return `${currencyCode} $${formatted}`
}

// localValue/usdValue are both already in their respective currency's
// units (i.e. localValue is NOT the USD amount multiplied by a rate the
// caller still needs to apply — pass the already-converted local amount).
export function formatDualCurrency(localValue, localCurrencyCode, usdValue, options = {}) {
  if (localCurrencyCode === 'USD') return formatCurrencyValue(usdValue, 'USD', options)
  return `${formatCurrencyValue(localValue, localCurrencyCode, options)} (${formatCurrencyValue(usdValue, 'USD', options)})`
}
