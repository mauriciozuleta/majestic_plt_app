import { isColombiaLocation } from '../services/colombiaPayrollTax'
import { isStMaartenLocation } from '../services/stMaartenPayrollTax'
import { formatCurrencyValue } from './currencyFormat'

const WHOLE_NUMBER_OPTIONS = { minimumFractionDigits: 0, maximumFractionDigits: 0 }

// For a single position's own location — returns the formatted local-
// currency string, or null if the position's location is USD-denominated
// (or unrecognized).
export function formatLocalCurrencyForLocation(location, usdAmount, rates) {
  if (isColombiaLocation(location)) {
    return formatCurrencyValue(usdAmount * rates.copPerUsd, 'COP', WHOLE_NUMBER_OPTIONS)
  }
  if (isStMaartenLocation(location)) {
    return formatCurrencyValue(usdAmount * rates.angPerUsd, 'ANG', WHOLE_NUMBER_OPTIONS)
  }
  return null
}

// For an aggregate across many rows that may mix countries — sums
// whichever non-USD-country rows are present and returns one formatted
// string per currency that actually contributed (empty array if
// everything in the set is USD).
export function formatLocalCurrencyForRows(rows, valueSelector, rates) {
  const colombiaTotal = rows
    .filter((row) => isColombiaLocation(row.location))
    .reduce((sum, row) => sum + valueSelector(row), 0)
  const stMaartenTotal = rows
    .filter((row) => isStMaartenLocation(row.location))
    .reduce((sum, row) => sum + valueSelector(row), 0)

  const parts = []
  if (colombiaTotal > 0) parts.push(formatCurrencyValue(colombiaTotal * rates.copPerUsd, 'COP', WHOLE_NUMBER_OPTIONS))
  if (stMaartenTotal > 0) parts.push(formatCurrencyValue(stMaartenTotal * rates.angPerUsd, 'ANG', WHOLE_NUMBER_OPTIONS))
  return parts
}
