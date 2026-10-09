import { formatCurrencyValue } from '../../utils/currencyFormat'

// The five displayed indicators (GDP is the supporting field of the dependency ratio).
export const TOURISM_INDICATORS = [
  { code: 'TOURISM_GDP_TOTAL_PCT', label: 'Tourism GDP % (total)', title: 'TOTAL contribution of travel & tourism to GDP (WTTC licensed data)', kind: 'pct' },
  { code: 'TOURISM_GDP_DIRECT_PCT', label: 'Tourism GDP % (direct)', title: 'Tourism DIRECT GDP as a proportion of total GDP (UN SDG 8.9.1, series ST_GDP_ZS). Not the total contribution.', kind: 'pct' },
  { code: 'TOURISM_EMPLOYMENT', label: 'Tourism Employment %', title: 'Total contribution of travel & tourism to employment (WTTC)', kind: 'pct' },
  { code: 'TOURISM_RECEIPTS', label: 'Tourism Receipts USD', title: 'International tourism receipts (World Bank)', kind: 'usd' },
  { code: 'TOURISM_DEPENDENCY', label: 'Tourism Dependency %', title: 'International tourism receipts / GDP x 100 (calculated, same year)', kind: 'pct' },
  { code: 'POPULATION', label: 'Population', title: 'Total population (World Bank)', kind: 'count' },
]

function compact(value) {
  const abs = Math.abs(value)
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return String(Math.round(value))
}

// kind: 'pct' | 'usd' | 'count'. Currency follows the app convention (code before the $, en-US separators).
export function formatTourismValue(kind, value, { short = false } = {}) {
  if (value == null) return 'N/A'
  if (kind === 'pct') return `${Number(value).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`
  if (kind === 'usd') return short ? `USD $${compact(value)}` : formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  return short ? compact(value) : Math.round(value).toLocaleString('en-US')
}

export function cellTooltip(cell) {
  if (!cell) return ''
  if (cell.value == null) return cell.reason || 'Not available'
  const parts = [`${cell.year}`, cell.source, cell.dataset, cell.edition && `edition ${cell.edition}`, cell.status].filter(Boolean)
  return `${parts.join(' · ')}${cell.note ? `\n${cell.note}` : ''}`
}

export const STATUS_CLASS = {
  Verified: 'is-verified',
  Calculated: 'is-calculated',
  Estimated: 'is-estimated',
  Historical: 'is-historical',
  Missing: 'is-missing',
  'Requires Review': 'is-review',
}
