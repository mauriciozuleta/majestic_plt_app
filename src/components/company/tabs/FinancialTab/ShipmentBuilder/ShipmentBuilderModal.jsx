import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchMarketAnalysisRegions } from '../../../../../services/commercialStructure'
import { fetchCountryProductPrices, fetchMarketOpportunityPriority, getOrComputeComparison } from '../../../../../services/marketOpportunities'
import { fetchMarketOpportunitySettings, marketLevelFor, suggestedSellPrice, UNMATCHED_MARKET_KEY } from '../../../../../services/marketOpportunitySettings'
import { fetchTaxMultipliers, productKey } from '../../../../../services/taxMultipliers'
import { fetchProductSam } from '../../../../../services/globalTradeData'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import { ALL_RATINGS, NO_SAM_CAP_KG, SAM_CAP_KG, allocateShipment, groupProductsByRating } from './shipmentBuilder'
import './ShipmentBuilder.css'

const STEP_LABELS = {
  resolving: 'Finding the route’s countries…',
  priority: 'Looking for the route’s priority list…',
  checking: 'Looking for a saved Market Opportunities comparison…',
  computing: 'No saved comparison — running it now (this can take a few minutes)…',
  sam: 'Loading each product’s Country SAM…',
}

const formatSam = (value) => (value == null ? '—' : formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 }))
const formatDiff = (value) => (value == null ? '—' : `${value.toFixed(1)}%`)

// Shipment builder for one route's outbound leg: the products on the
// priority list of the origin country -> destination country comparison
// (Market Analysis ▸ Market Opportunities), grouped by rating and ordered by
// Country SAM then Diff % (see shipmentBuilder.js), for selection. With no
// priority list yet, it points to Market Opportunities to build one.
// `capacityKg` is the aircraft's max payload; `previous` the route's last
// built shipment (its products start ticked instead of every product).
// `onBuild(shipment)` saves the distribution.
// `airfarePerKg` is the leg's Price x Kg: with it, each product's DDP price (and so its market level) can be worked out.
function ShipmentBuilderModal({ origin, destination, capacityKg, aircraftName, airfarePerKg, previous, onBuild, onClose }) {
  const navigate = useNavigate()
  const [step, setStep] = useState('resolving')
  const [error, setError] = useState('')
  const [countries, setCountries] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [productSam, setProductSam] = useState(null)
  const [samError, setSamError] = useState('')
  const [selected, setSelected] = useState(() => new Set())
  // Priority products no longer in the comparison (recomputed since they were added)
  const [missingPriority, setMissingPriority] = useState([])
  // Settings ▸ Destination Market (ranges + cargo caps), the tax multipliers of the pair, and the priority-list products that have no
  // match in the target market (they ship as niche market products)
  const [destinationMarkets, setDestinationMarkets] = useState([])
  const [multipliers, setMultipliers] = useState(() => new Map())
  const [unmatchedProducts, setUnmatchedProducts] = useState([])
  const [building, setBuilding] = useState(false)
  const [buildError, setBuildError] = useState('')

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

      setStep('priority')
      const priority = await fetchMarketOpportunityPriority(source.name, [target.name])
      if (cancelled) return
      const priorityNames = new Set(priority.items.filter((item) => item.target_country === target.name).map((item) => item.product_name))
      if (priorityNames.size === 0) {
        setStep('no-priority')
        return
      }

      setStep('checking')
      const result = await getOrComputeComparison(source.name, [target.name], {
        onStatus: (status) => !cancelled && status === 'computing' && setStep('computing'),
      })
      if (cancelled) return
      const rows = result.rows.filter((row) => priorityNames.has(row.product_name))
      const found = new Set(rows.map((row) => row.product_name))
      const notInComparison = [...priorityNames].filter((name) => !found.has(name))
      // Priority-list products with no match in the target market: from the source portfolio (price, HS code)
      let noMatch = []
      if (notInComparison.length) {
        const portfolio = await fetchCountryProductPrices(source.name).catch(() => [])
        const byKey = new Map(portfolio.map((product) => [productKey(product.name), product]))
        noMatch = notInComparison.map((name) => byKey.get(productKey(name))).filter(Boolean)
      }
      const [settings, taxMap] = await Promise.all([
        fetchMarketOpportunitySettings().catch(() => ({ destination_markets: [] })),
        fetchTaxMultipliers(target.name, source.name).catch(() => new Map()),
      ])
      if (cancelled) return
      setDestinationMarkets(settings.destination_markets || [])
      setMultipliers(taxMap)
      setUnmatchedProducts(noMatch)
      const noMatchNames = new Set(noMatch.map((product) => product.name.toLowerCase()))
      setMissingPriority(notInComparison.filter((name) => !noMatchNames.has(name.toLowerCase())))
      setComparison({ ...result, rows })
      // Every product starts ticked — or, when updating, the ones in the last shipment.
      const previousNames = new Set((previous?.items || []).map((item) => item.product_name))
      setSelected(
        new Set([
          ...rows.filter((row) => !previousNames.size || previousNames.has(row.product_name)).map((row) => `${row.product_name}|${row.hs_code ?? ''}`),
          ...noMatch.filter((product) => !previousNames.size || previousNames.has(product.name)).map((product) => `${product.name}|${product.hsCode ?? ''}`),
        ]),
      )

      setStep('sam')
      const codes = [...new Set([...rows.map((row) => row.hs_code), ...noMatch.map((product) => product.hsCode)].filter((code) => /^\d{6}$/.test(code || '')))]
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
  }, [origin, destination, previous])

  const cargoCapOf = (key) => destinationMarkets.find((market) => market.key === key)?.cargo_cap_kg ?? null
  const marketLabelOf = (key) => destinationMarkets.find((market) => market.key === key)?.label ?? null
  const groups = useMemo(() => {
    if (!comparison || !countries) return []
    const samFor = (hsCode) => productSam?.products?.[hsCode]?.countries?.[countries.target.name]?.value ?? null
    // market level of a matched product: its DDP price per kg as a % of the target price, against the Destination Market ranges
    const levelFor = (row) => {
      const multiplier = multipliers.get(productKey(row.product_name))?.tax_multiplier ?? null
      const ddp = airfarePerKg != null && multiplier != null && row.source_price_normalized != null ? (row.source_price_normalized + airfarePerKg) * (1 + multiplier) : null
      const { key, level, cargoCapKg } = marketLevelFor(ddp, row.target_price_normalized, destinationMarkets)
      // A wholesale product with a thin profit margin ((sale price - cost) / cost, the sale price being the suggested one) is shipped
      // less: its cap loses the wholesalers' cap reduction (Settings ▸ Destination Market ▸ Min profit margin / Cap reduction).
      const market = destinationMarkets.find((item) => item.key === key)
      let capKg = cargoCapKg
      let marginPct = null
      let capReduced = false
      if (key === 'wholesalers' && ddp != null) {
        const sale = suggestedSellPrice(key, ddp, row.target_price_normalized, destinationMarkets).value
        marginPct = sale != null && ddp > 0 ? ((sale - ddp) / ddp) * 100 : null
        if (marginPct != null && market?.min_margin_pct != null && market?.cap_reduction_kg && marginPct < market.min_margin_pct) {
          const sam = samFor(row.hs_code)
          capKg = Math.max(0, (cargoCapKg ?? (sam > 0 ? SAM_CAP_KG : NO_SAM_CAP_KG)) - market.cap_reduction_kg)
          capReduced = true
        }
      }
      return { marketKey: key, marketLevel: level, capKg, marginPct, capReduced }
    }
    const list = groupProductsByRating(comparison.rows, (row) => samFor(row.hs_code), ALL_RATINGS, levelFor)
    if (unmatchedProducts.length) {
      const extra = unmatchedProducts.map((product) => ({
        key: `${product.name}|${product.hsCode ?? ''}`,
        hsCode: product.hsCode,
        productName: product.name,
        targetProductName: null,
        diffPct: null,
        opportunityRating: 'Unrated',
        countrySam: samFor(product.hsCode),
        marketKey: UNMATCHED_MARKET_KEY,
        marketLevel: marketLabelOf(UNMATCHED_MARKET_KEY) ?? 'Niche Markets',
        capKg: cargoCapOf(UNMATCHED_MARKET_KEY),
        noMatch: true,
      }))
      const unrated = list.find((group) => group.rating === 'Unrated')
      if (unrated) unrated.products.push(...extra)
      else list.push({ rating: 'Unrated', products: extra })
    }
    return list
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the helpers read destinationMarkets, listed here
  }, [comparison, countries, productSam, multipliers, destinationMarkets, unmatchedProducts, airfarePerKg])
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
  const chosen = products.filter((item) => selected.has(item.key))
  const build = async () => {
    // weights typed in by hand (Details ▸ Edit) in the shipment being updated stay as they are
    const fixed = new Map((previous?.items || []).filter((item) => item.manual).map((item) => [`${item.product_name}|${item.hs_code ?? ''}`, item.kg]))
    const { items } = allocateShipment(chosen, capacityKg, fixed)
    setBuilding(true)
    setBuildError('')
    try {
      await onBuild({
        capacity_kg: capacityKg,
        aircraft_name: aircraftName || null,
        items: items.map((item) => ({
          product_name: item.productName,
          hs_code: item.hsCode || null,
          target_product_name: item.targetProductName || null,
          kg: item.kg,
          share_pct: Math.round(item.sharePct * 10) / 10,
          country_sam: item.countrySam,
          diff_pct: item.diffPct,
          rating: item.opportunityRating,
          manual: item.manual || false,
        })),
      })
    } catch (err) {
      setBuildError(err.message)
      setBuilding(false)
    }
  }
  const openMarketOpportunities = () => {
    const params = new URLSearchParams({ tab: 'market-opportunities' })
    if (countries) {
      params.set('source', countries.source.name)
      params.set('target', countries.target.name)
    }
    onClose()
    navigate(`/market-analysis?${params.toString()}`)
  }

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
        {step === 'no-priority' && countries && (
          <div className="shipment-builder__empty">
            <p>
              There's no priority list for <strong>{countries.source.name} → {countries.target.name}</strong> yet.
            </p>
            <p className="shipment-builder__status">
              Build it in Market Analysis ▸ Market Opportunities: tick the products you want to ship and press Add to priority list.
            </p>
            <button type="button" className="shipment-builder__button shipment-builder__button--primary" onClick={openMarketOpportunities}>
              Go to Market Opportunities
            </button>
          </div>
        )}
        {STEP_LABELS[step] && <p className="shipment-builder__status">{STEP_LABELS[step]}</p>}

        {step === 'ready' && comparison && (
          <>
            <p className="shipment-builder__meta">
              Priority list · {products.length} product{products.length === 1 ? '' : 's'} by rating, then Country SAM and Diff % · comparison
              {comparison.calculatedAt && ` computed ${new Date(comparison.calculatedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`}
              {selected.size > 0 && ` · ${selected.size} selected`}
              {' · '}
              <button type="button" className="shipment-builder__link" onClick={openMarketOpportunities}>
                Edit the priority list
              </button>
            </p>
            {missingPriority.length > 0 && (
              <p className="shipment-builder__status">
                Not in the latest comparison any more: {missingPriority.join(', ')}.
              </p>
            )}
            {samError && <p className="shipment-builder__error">Country SAM didn’t load ({samError}).</p>}
            {products.length === 0 ? (
              <p className="shipment-builder__status">None of the priority list's products are in the latest comparison.</p>
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
                      <th>Market level</th>
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
                        <td colSpan={5}>
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
                        <td title={item.targetProductName ? `Matched in ${countries.target.name}: ${item.targetProductName}` : item.noMatch ? `No match in ${countries.target.name}` : undefined}>{item.productName}</td>
                        <td className="is-num">{formatSam(item.countrySam)}</td>
                        <td className="is-num" title={item.opportunityRating || undefined}>
                          {formatDiff(item.diffPct)}
                        </td>
                        <td
                          title={
                            item.noMatch
                              ? 'No match in the target market — a niche market product'
                              : item.capReduced
                                ? `Profit margin ${item.marginPct.toFixed(2)}% is under the minimum: the cap is reduced to ${Math.round(item.capKg).toLocaleString('en-US')} kg`
                                : item.marginPct != null
                                  ? `Profit margin ${item.marginPct.toFixed(2)}%`
                                  : undefined
                          }
                        >
                          {item.marketLevel || '—'}
                          {item.capReduced ? ' ↓' : ''}
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

        {step === 'ready' && products.length > 0 && (
          <p className="shipment-builder__status">
            Build ships every ticked product, filling {capacityKg ? `${Math.round(capacityKg).toLocaleString('en-US')} kg` : 'the aircraft'}: first every wholesaler gets its full cap,
            then every premium product its cap, and the niche products split what is left (a market&apos;s cap is its Cargo Cap in Settings, otherwise{' '}
            {SAM_CAP_KG.toLocaleString('en-US')} kg, or {NO_SAM_CAP_KG} kg without a Country SAM). If the caps add up to more than the aircraft carries, the last group
            shares what is left evenly — nobody is dropped.
            {airfarePerKg == null && ' The route has no air fare (Price x Kg) yet, so market levels can’t be worked out and every product is treated alike.'}
          </p>
        )}
        {buildError && <p className="shipment-builder__error">{buildError}</p>}
        <footer className="shipment-builder__footer">
          {step === 'ready' && products.length > 0 && (
            <button
              type="button"
              className="shipment-builder__button shipment-builder__button--primary"
              onClick={build}
              disabled={!chosen.length || !capacityKg || building}
              title={capacityKg ? undefined : "The route's aircraft has no max payload to fill"}
            >
              {building ? 'Building…' : `Build${chosen.length ? ` (${chosen.length})` : ''}`}
            </button>
          )}
          <button type="button" className="shipment-builder__button" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  )
}

export default ShipmentBuilderModal
