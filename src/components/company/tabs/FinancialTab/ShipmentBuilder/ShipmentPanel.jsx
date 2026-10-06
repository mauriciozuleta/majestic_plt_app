import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchMarketAnalysisRegions } from '../../../../../services/commercialStructure'
import { fetchMarketOpportunityComparisons } from '../../../../../services/marketOpportunities'
import { fetchTaxMultipliers, formatMultiplier, productKey } from '../../../../../services/taxMultipliers'
import { formatCurrencyValue } from '../../../../../utils/currencyFormat'
import './ShipmentPanel.css'

const usd = (value) => (value == null ? '—' : formatCurrencyValue(value, 'USD'))
const usd0 = (value) => (value == null ? '—' : formatCurrencyValue(value, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 }))
const kgText = (value) => `${Math.round(value).toLocaleString('en-US')} kg`
const pct = (value, digits = 1) => Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

// The Market Opportunities comparison page of a leg's countries (optionally pointing at one product).
const marketOpportunitiesUrl = (countries, productName) => {
  const params = new URLSearchParams({ tab: 'market-opportunities' })
  if (countries) {
    params.set('source', countries.source)
    params.set('target', countries.target)
  }
  if (productName) params.set('product', productName)
  return `/market-analysis?${params.toString()}`
}

// The cost chain of one product of a built shipment:
//   FCA = kg x the origin country's price per kg (the one the saved Market Opportunities comparison used)
//   DAP = kg x the leg's price per kg (air fare); DAP subtotal = FCA + DAP
//   DDP at Terminal = DAP subtotal x the product's tax multiplier (Market Opportunities
//   origin -> destination comparison); DDP total = DAP subtotal + those taxes.
// Any figure that can't be worked out is null.
function costsFor(item, { prices, multipliers, airfarePerKg }) {
  const price = prices?.get(productKey(item.product_name))?.priceUsdPerKg ?? null
  const fcaPerKg = price
  const fca = fcaPerKg != null ? item.kg * fcaPerKg : null
  const dap = airfarePerKg != null ? item.kg * airfarePerKg : null
  const subtotal = fca != null && dap != null ? fca + dap : null
  const multiplier = multipliers?.get(productKey(item.product_name))?.tax_multiplier ?? null
  const taxes = subtotal != null && multiplier != null ? subtotal * multiplier : null
  const ddp = subtotal != null && taxes != null ? subtotal + taxes : null
  return { fcaPerKg, fca, dap, subtotal, multiplier, taxes, ddp }
}

// The built shipment of one leg as small cards, across the whole card row. `origin` and `destination` are
// the leg's branches (their countries drive the price list and the tax multipliers); `airfarePerKg` is the
// leg's Price x Kg.
function ShipmentPanel({ shipment, legTitle, origin, destination, airfarePerKg, airfareNote }) {
  const navigate = useNavigate()
  const [context, setContext] = useState({ loading: true, error: '', countries: null, prices: null, multipliers: null })
  const [detailItem, setDetailItem] = useState(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const regions = await fetchMarketAnalysisRegions()
      const locate = (branch) => {
        for (const row of regions) {
          const country = row.countries.find((entry) => entry.id === branch?.country_id)
          if (country) return country.name
        }
        return null
      }
      const source = locate(origin)
      const target = locate(destination)
      if (!source || !target) throw new Error('The leg’s airports aren’t in an active Market Analysis country.')
      const [prices, multipliers] = await Promise.all([
        fetchMarketOpportunityComparisons(source, [target]).then(
          (saved) => new Map((saved.rows || []).map((row) => [productKey(row.product_name), { priceUsdPerKg: row.source_price_normalized }])),
        ),
        fetchTaxMultipliers(target, source).catch(() => new Map()),
      ])
      if (!cancelled) setContext({ loading: false, error: '', countries: { source, target }, prices, multipliers })
    }
    run().catch((err) => !cancelled && setContext({ loading: false, error: err?.message || 'Could not load the costs.', countries: null, prices: null, multipliers: null }))
    return () => {
      cancelled = true
    }
  }, [origin, destination])

  const allocated = shipment.items.reduce((sum, item) => sum + item.kg, 0)
  const costs = useMemo(
    () => new Map(shipment.items.map((item) => [item, costsFor(item, { prices: context.prices, multipliers: context.multipliers, airfarePerKg })])),
    [shipment, context, airfarePerKg],
  )
  const ddpTotal = useMemo(() => {
    const all = [...costs.values()]
    return all.length && all.every((cost) => cost.ddp != null) ? all.reduce((sum, cost) => sum + cost.ddp, 0) : null
  }, [costs])

  const openMarketOpportunities = (productName) => navigate(marketOpportunitiesUrl(context.countries, productName))

  return (
    <div className={`revenue-streams-view__shipment ${legTitle === 'Return' ? 'is-return' : ''}`}>
      <div className="revenue-streams-view__shipment-head">
        <strong>{legTitle} shipment</strong> · {kgText(allocated)} of {kgText(shipment.capacity_kg)} ({pct((allocated / shipment.capacity_kg) * 100)}%) ·{' '}
        {shipment.items.length} products
        {shipment.aircraft_name && ` · ${shipment.aircraft_name}`}
        {shipment.built_at && ` · built ${new Date(shipment.built_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`}
        {shipment.capacity_kg - allocated >= 1 && ` · ${kgText(shipment.capacity_kg - allocated)} unallocated (product limits reached)`}
        {ddpTotal != null && ` · DDP total ${usd0(ddpTotal)}`}
      </div>
      {context.error && <div className="shipment-panel__error">{context.error}</div>}
      <div className="revenue-streams-view__shipment-cards">
        {shipment.items.map((item) => {
          const cost = costs.get(item)
          return (
            <div
              key={`${item.product_name}|${item.hs_code ?? ''}`}
              className="revenue-streams-view__shipment-card"
              title={[
                item.target_product_name && `Matched: ${item.target_product_name}`,
                item.hs_code && `HS ${item.hs_code}`,
                item.rating && `Rating: ${item.rating}`,
                `${pct(item.share_pct ?? 0)}% of the shipment`,
                `SAM ${item.country_sam != null ? formatCurrencyValue(item.country_sam, 'USD', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) : '—'}`,
                `Diff ${item.diff_pct != null ? `${pct(item.diff_pct)}%` : '—'}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            >
              <Link
                className="revenue-streams-view__shipment-name shipment-panel__product-link"
                to={marketOpportunitiesUrl(context.countries, item.product_name)}
                title="Open this comparison in Market Opportunities"
              >
                {item.product_name}
              </Link>
              <span className="revenue-streams-view__shipment-kg">
                {kgText(item.kg)} / {context.loading ? '…' : usd0(cost.ddp)}
              </span>
              <button type="button" className="shipment-panel__details-btn" onClick={() => setDetailItem(item)}>
                Details
              </button>
            </div>
          )
        })}
      </div>
      {detailItem && (
        <ProductDetails
          item={detailItem}
          cost={costs.get(detailItem)}
          countries={context.countries}
          airfarePerKg={airfarePerKg}
          airfareNote={airfareNote}
          legTitle={legTitle}
          onOpenMarketOpportunities={() => openMarketOpportunities(detailItem.product_name)}
          onClose={() => setDetailItem(null)}
        />
      )}
    </div>
  )
}

function ProductDetails({ item, cost, countries, airfarePerKg, airfareNote, legTitle, onOpenMarketOpportunities, onClose }) {
  const noMultiplier = cost.multiplier == null
  return (
    <div className="shipment-panel__overlay" role="dialog" aria-modal="true" aria-label={`${item.product_name} details`} onClick={onClose}>
      <div className="shipment-panel__modal" onClick={(event) => event.stopPropagation()}>
        <header className="shipment-panel__modal-head">
          <div>
            <span className="shipment-panel__eyebrow">{legTitle} shipment{countries ? ` · ${countries.source} → ${countries.target}` : ''}</span>
            <h3>{item.product_name}</h3>
            <span className="shipment-panel__sub">{kgText(item.kg)}{item.hs_code ? ` · HS ${item.hs_code}` : ''}</span>
          </div>
          <button type="button" className="shipment-panel__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <section className="shipment-panel__section">
          <h4>FCA cost</h4>
          <p>Price x kg = {usd(cost.fcaPerKg)}</p>
          <p>
            Total = <strong>{usd(cost.fca)}</strong>
          </p>
          {cost.fcaPerKg == null && <p className="shipment-panel__warn">No price per kg for this product in the {countries ? `${countries.source} → ${countries.target}` : 'origin → destination'} Market Opportunities comparison.</p>}
        </section>

        <section className="shipment-panel__section">
          <h4>DAP cost</h4>
          <p>Price x kg (air fare) = {usd(airfarePerKg)}</p>
          <p>
            Total = <strong>{usd(cost.dap)}</strong>
          </p>
          {airfarePerKg == null && <p className="shipment-panel__warn">{airfareNote || 'This leg has no price per kg yet.'}</p>}
          <p className="shipment-panel__subtotal">
            Total DAP (FCA + DAP) = <strong>{usd(cost.subtotal)}</strong>
          </p>
        </section>

        <section className="shipment-panel__section">
          <h4>DDP at Terminal</h4>
          {noMultiplier ? (
            <div className="shipment-panel__alert" role="alert">
              <strong>No tax multiplier for this product.</strong> The {countries ? `${countries.source} → ${countries.target}` : 'origin → destination'} comparison in Market
              Opportunities hasn’t produced one — build it there first.
              <button type="button" className="shipment-panel__alert-btn" onClick={onOpenMarketOpportunities}>
                Go to Market Opportunities
              </button>
            </div>
          ) : (
            <>
              <p>TAX {formatMultiplier(cost.multiplier)}</p>
              <p>
                Total = <strong>{usd(cost.taxes)}</strong>
              </p>
            </>
          )}
          <p className="shipment-panel__subtotal">
            DDP total (DAP + taxes) = <strong>{usd(cost.ddp)}</strong>
          </p>
        </section>
      </div>
    </div>
  )
}

export default ShipmentPanel
