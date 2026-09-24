import { useEffect, useMemo, useState } from 'react'
import { fetchCustomSourceProducts } from '../../../../../services/productSources'
import { fetchExchangeRate } from '../../../../../services/exchangeRate'
import { buildProductCodeIndex } from '../../../../../services/productPortfolio'
import { formatCurrencyValue, formatDualCurrency } from '../../../../../utils/currencyFormat'

const muted = { color: '#8ea3c2', margin: 0 }

// App-wide currency convention: code before "$", en-US separators, and the
// USD equivalent in parentheses for non-USD currencies (when a rate loaded).
function formatPrice(value, currency, usdRates) {
  if (!currency) return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })
  const rate = usdRates[currency]
  if (currency === 'USD') return formatCurrencyValue(value, 'USD')
  return rate ? formatDualCurrency(value, currency, value * rate) : formatCurrencyValue(value, currency)
}

function priceLevelLabel(analysisType) {
  return analysisType === 'retail' ? 'Retail' : 'Wholesaler'
}

// Products from every source added in Settings ▸ Product analysis sources
// (website analysed, or a loaded file) for one country, all together —
// each source's own Wholesaler/Retail checkbox (see ProductSourcesCard.jsx)
// shows up as a label next to it here, not as a filter. Prices are shown as
// the source quotes them — its own unit and currency — with no conversion,
// unlike the built-in Colombia/USA views which normalise to per-kg.
// `highlightHsCode` (from Available Categories' country-code links, via
// MarketAnalysisPanel) filters straight down to the product(s) whose own
// reference code (see productPortfolio.js — countryCode+hs_code) falls
// under this HS code, on top of (not instead of) the text search box
// already here. The parent remounts this view (new key) on every new
// click, so a plain useState seeded from the prop is enough — no effect
// needed to react to it changing.
function CustomSourceProductsView({ countryName, companyId, showEmptyHint = true, highlightHsCode = null }) {
  const [sources, setSources] = useState([])
  const [status, setStatus] = useState('loading')
  const [search, setSearch] = useState('')
  const [usdRates, setUsdRates] = useState({})
  const [productCodes, setProductCodes] = useState(new Map())
  const [highlightCleared, setHighlightCleared] = useState(false)
  const highlightActive = Boolean(highlightHsCode) && !highlightCleared

  useEffect(() => {
    let cancelled = false
    fetchCustomSourceProducts()
      .then((rows) => {
        if (cancelled) return
        const mine = rows.filter((row) => row.country_name.trim().toLowerCase() === countryName.trim().toLowerCase())
        setSources(mine)
        setStatus('ready')
        const currencies = [...new Set(mine.flatMap((row) => row.products.map((p) => p.currency)).filter((c) => c && c !== 'USD'))]
        currencies.forEach((code) =>
          fetchExchangeRate(code, 'USD')
            .then(({ rate }) => !cancelled && setUsdRates((prev) => ({ ...prev, [code]: rate })))
            .catch(() => {}),
        )
      })
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [countryName])

  // Same reference-code lookup as the Colombia/USA views (see
  // productPortfolio.js) — gated on companyId so it doesn't run before a
  // company workspace is actually selected.
  useEffect(() => {
    if (!companyId) return undefined
    let cancelled = false
    buildProductCodeIndex()
      .then((index) => {
        if (!cancelled) setProductCodes(index)
      })
      .catch(() => {
        // Non-fatal: the table still works without the reference codes.
      })
    return () => {
      cancelled = true
    }
  }, [companyId, sources])

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return sources
      .flatMap((source) =>
        source.products.map((product) => ({ ...product, sourceName: source.source_name, priceLevel: priceLevelLabel(source.analysis_type) })),
      )
      .filter((row) => !needle || row.name.toLowerCase().includes(needle) || row.category.toLowerCase().includes(needle))
      .filter((row) => {
        if (!highlightActive) return true
        // A code is the country's ISO2 + the real HS code (see
        // productPortfolio.js) — strip the 2-letter prefix and match the
        // rest against the clicked HS code as a prefix (a 6-digit
        // highlight still matches a longer real tariff code that starts
        // with it).
        const code = productCodes.get(row.name.toLowerCase())
        return code && code.slice(2).startsWith(highlightHsCode)
      })
  }, [sources, search, highlightActive, highlightHsCode, productCodes])

  const hasRange = rows.some((row) => row.low != null || row.high != null)
  const asOf = [...new Set(sources.flatMap((source) => source.products.map((p) => p.as_of)).filter(Boolean))]

  if (status === 'loading') return <p style={muted}>Loading sources…</p>
  if (status === 'error') return <p style={muted}>Could not load the added sources.</p>
  if (sources.length === 0) {
    return showEmptyHint ? (
      <p style={muted}>
        Product analysis is not yet available for {countryName}. Add a source in Settings → Product analysis sources — a
        website to analyse, or a products file to load.
      </p>
    ) : null
  }

  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {highlightActive && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 12px',
            borderRadius: '8px',
            border: '1px solid rgba(53, 211, 153, 0.35)',
            background: 'rgba(53, 211, 153, 0.1)',
            color: '#6ee7b7',
            fontSize: '0.82rem',
          }}
        >
          Showing products classified under HS code {highlightHsCode} (from Available Categories).
          <button
            type="button"
            onClick={() => setHighlightCleared(true)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}
          >
            Clear filter
          </button>
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px' }}>
        <strong style={{ color: '#e6edf8' }}>Added sources</strong>
        <span style={{ ...muted, fontSize: '0.8rem' }}>
          {sources.map((source) => `${source.source_name} (${priceLevelLabel(source.analysis_type)}, ${source.products.length})`).join(' · ')}
          {asOf.length > 0 && ` · week ending ${asOf.join(' / ')}`}
        </span>
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search products…"
          style={{ marginLeft: 'auto', minWidth: '12rem' }}
        />
      </div>
      <div style={{ overflow: 'auto', maxHeight: '28rem', border: '1px solid #2a3f5c', borderRadius: '10px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', color: '#cfe0f8' }}>
          <thead>
            <tr style={{ position: 'sticky', top: 0, background: '#111f31', textAlign: 'left' }}>
              {['Code', 'Product', 'Category', 'Source', 'Unit', 'Price', ...(hasRange ? ['Range'] : [])].map((label) => (
                <th key={label} style={{ padding: '8px 10px', fontSize: '0.7rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: '#8ea3c2' }}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.sourceName}-${row.id}-${index}`} style={{ borderTop: '1px solid #1c2c44' }}>
                <td style={{ padding: '7px 10px', color: '#8ea3c2' }}>{productCodes.get(row.name.toLowerCase()) || '—'}</td>
                <td style={{ padding: '7px 10px' }}>{row.name}</td>
                <td style={{ padding: '7px 10px', color: '#8ea3c2' }}>{row.category}</td>
                <td style={{ padding: '7px 10px', color: '#8ea3c2' }}>
                  {row.sourceName} <span style={{ opacity: 0.7 }}>({row.priceLevel})</span>
                </td>
                <td style={{ padding: '7px 10px', color: '#8ea3c2' }}>{row.unit}</td>
                <td style={{ padding: '7px 10px', fontVariantNumeric: 'tabular-nums' }}>{formatPrice(row.price, row.currency, usdRates)}</td>
                {hasRange && (
                  <td style={{ padding: '7px 10px', color: '#8ea3c2', fontVariantNumeric: 'tabular-nums' }}>
                    {row.low != null && row.high != null
                      ? `${row.low.toLocaleString('en-US')} – ${row.high.toLocaleString('en-US')}${row.markets ? ` (${row.markets} ${row.markets === 1 ? 'market' : 'markets'})` : ''}`
                      : '—'}
                  </td>
                )}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={hasRange ? 7 : 6} style={{ padding: '12px', ...muted }}>
                  No products match "{search}".
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default CustomSourceProductsView
