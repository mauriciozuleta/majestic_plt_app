import { useEffect, useMemo, useState } from 'react'
import { fetchMarketAnalysisRegions } from '../../../../../services/commercialStructure'
import { getOrComputeComparison } from '../../../../../services/marketOpportunities'
import { fetchProductSam } from '../../../../../services/globalTradeData'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { SHIPMENT_RATINGS, groupProductsByRating } from './shipmentBuilder'
import './ShipmentBuilder.css'

const STEP_LABELS = {
  resolving: 'Finding the route’s countries…',
  checking: 'Looking for a saved Market Opportunities comparison…',
  computing: 'No saved comparison — running it now (this can take a few minutes)…',
  sam: 'Loading each product’s Country SAM…',
}

const formatSam = (value) => (value == null ? '—' : formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 }))
const formatDiff = (value) => (value == null ? '—' : `${value.toFixed(1)}%`)

// Shipment builder for one route's outbound leg: finds (or runs) the Market
// Opportunities comparison of the origin country against the destination
// country, then lists its Very High / High / Challenging products, each
// rating ordered by Country SAM then Diff % (see shipmentBuilder.js), for
// selection.
function ShipmentBuilderModal({ origin, destination, onClose }) {
  const [step, setStep] = useState('resolving')
  const [error, setError] = useState('')
  const [countries, setCountries] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [productSam, setProductSam] = useState(null)
  const [samError, setSamError] = useState('')
  const [selected, setSelected] = useState(() => new Set())

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      // A branch's country_id is the commercial-structure country the
      // Market Analysis regions list carries.
      const regions = await fetchMarketAnalysisRegions()
      const locate = (branch) => {
        for (const row of regions) {
          const country = row.countries.find((item) => item.id === branch?.country_id)
          if (country) return { name: country.name, region: row.region }
        }
        return null
      }
      const source = locate(origin)
      const target = locate(destination)
      if (!source || !target) throw new Error('The origin or destination airport isn’t in an active Market Analysis country.')
      if (source.name === target.name) throw new Error('Origin and destination are in the same country — there is nothing to compare.')
      if (cancelled) return
      setCountries({ source, target })

      setStep('checking')
      const result = await getOrComputeComparison(source.name, [target.name], {
        onStatus: (status) => !cancelled && status === 'computing' && setStep('computing'),
      })
      if (cancelled) return
      setComparison(result)

      setStep('sam')
      const codes = [...new Set(result.rows.map((row) => row.hs_code).filter((code) => /^\d{6}$/.test(code || '')))]
      if (codes.length) {
        try {
          const sam = await fetchProductSam(target.region, codes)
          if (!cancelled) setProductSam(sam)
        } catch (err) {
          if (!cancelled) setSamError(err?.message || 'Could not load Country SAM.')
        }
      }
      if (!cancelled) setStep('ready')
    }
    run().catch((err) => {
      if (cancelled) return
      setError(err?.message || 'Could not build the product list.')
      setStep('error')
    })
    return () => {
      cancelled = true
    }
  }, [origin, destination])

  const groups = useMemo(() => {
    if (!comparison || !countries) return []
    return groupProductsByRating(comparison.rows, (row) => productSam?.products?.[row.hs_code]?.countries?.[countries.target.name]?.value ?? null)
  }, [comparison, countries, productSam])
  const products = useMemo(() => groups.flatMap((group) => group.products), [groups])

  const toggle = (key) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  // Select / clear a set of products at once (all of them, or one rating's).
  const isAllSelected = (items) => items.length > 0 && items.every((item) => selected.has(item.key))
  const toggleMany = (items) =>
    setSelected((prev) => {
      const next = new Set(prev)
      const select = !items.every((item) => next.has(item.key))
      items.forEach((item) => (select ? next.add(item.key) : next.delete(item.key)))
      return next
    })

  const title = countries ? `${countries.source.name} → ${countries.target.name}` : 'Shipment builder'

  return (
    <div className="shipment-builder__overlay" role="dialog" aria-modal="true" aria-label="Shipment builder">
      <div className="shipment-builder">
        <header className="shipment-builder__header">
          <div>
            <span className="shipment-builder__eyebrow">Shipment builder</span>
            <h3>{title}</h3>
          </div>
          <button type="button" className="shipment-builder__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {step === 'error' && <p className="shipment-builder__error">{error}</p>}
        {STEP_LABELS[step] && <p className="shipment-builder__status">{STEP_LABELS[step]}</p>}

        {step === 'ready' && comparison && (
          <>
            <p className="shipment-builder__meta">
              {comparison.origin === 'saved' ? 'Saved comparison' : 'Comparison just computed'}
              {comparison.calculatedAt && `, ${new Date(comparison.calculatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`} ·{' '}
              {products.length} product{products.length === 1 ? '' : 's'} rated {SHIPMENT_RATINGS.join(', ')}, each by Country SAM then Diff %
              {selected.size > 0 && ` · ${selected.size} selected`}
            </p>
            {samError && <p className="shipment-builder__error">Country SAM didn’t load ({samError}).</p>}
            {products.length === 0 ? (
              <p className="shipment-builder__status">No product between these two countries is rated {SHIPMENT_RATINGS.join(', ')}.</p>
            ) : (
              <div className="shipment-builder__table-wrap">
                <table className="shipment-builder__table">
                  <thead>
                    <tr>
                      <th className="shipment-builder__check-col">
                        <input type="checkbox" checked={isAllSelected(products)} onChange={() => toggleMany(products)} aria-label="Select all products" />
                      </th>
                      <th>HS code</th>
                      <th>Product</th>
                      <th className="is-num">Country SAM</th>
                      <th className="is-num">Diff %</th>
                    </tr>
                  </thead>
                  {groups.map((group) => (
                    <tbody key={group.rating}>
                      <tr className="shipment-builder__group-row">
                        <td className="shipment-builder__check-col">
                          <input
                            type="checkbox"
                            checked={isAllSelected(group.products)}
                            onChange={() => toggleMany(group.products)}
                            aria-label={`Select all ${group.rating} products`}
                          />
                        </td>
                        <td colSpan={4}>
                          <span className="shipment-builder__group-label">{group.rating}</span>
                          <span className="shipment-builder__group-count">
                            {group.products.length} product{group.products.length === 1 ? '' : 's'}
                          </span>
                        </td>
                      </tr>
                    {group.products.map((item) => (
                      <tr key={item.key} className={selected.has(item.key) ? 'is-selected' : ''} onClick={() => toggle(item.key)}>
                        <td className="shipment-builder__check-col">
                          <input
                            type="checkbox"
                            checked={selected.has(item.key)}
                            onChange={() => toggle(item.key)}
                            onClick={(event) => event.stopPropagation()}
                            aria-label={`Select ${item.productName}`}
                          />
                        </td>
                        <td className="shipment-builder__code">{item.hsCode || '—'}</td>
                        <td title={item.targetProductName ? `Matched in ${countries.target.name}: ${item.targetProductName}` : undefined}>{item.productName}</td>
                        <td className="is-num">{formatSam(item.countrySam)}</td>
                        <td className="is-num" title={item.opportunityRating || undefined}>
                          {formatDiff(item.diffPct)}
                        </td>
                      </tr>
                    ))}
                    </tbody>
                  ))}
                </table>
              </div>
            )}
          </>
        )}

        <footer className="shipment-builder__footer">
          <button type="button" className="shipment-builder__button" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default ShipmentBuilderModal
