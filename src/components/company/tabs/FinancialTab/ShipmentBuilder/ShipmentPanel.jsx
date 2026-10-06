import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchMarketOpportunitySettings } from '../../../../../services/marketOpportunitySettings'
import { formatMultiplier } from '../../../../../services/taxMultipliers'
import { financeForShipment, loadShipmentContext } from './shipmentFinance'
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

// The built shipment of one leg as small cards, across the whole card row. `origin` and `destination` are
// the leg's branches (their countries drive the price list and the tax multipliers); `airfarePerKg` is the
// leg's Price x Kg.
// `onSave(shipment)` stores an edited shipment (a weight typed in by hand) and rejects with the reason when it can't.
function ShipmentPanel({ shipment, legTitle, origin, destination, airfarePerKg, airfareNote, onSave }) {
  const navigate = useNavigate()
  const [context, setContext] = useState({ loading: true, error: '', countries: null, prices: null, multipliers: null })
  const [detailKey, setDetailKey] = useState(null)
  const detailItem = detailKey ? shipment.items.find((item) => `${item.product_name}|${item.hs_code ?? ''}` === detailKey) ?? null : null
  const [destinationMarkets, setDestinationMarkets] = useState([])
  useEffect(() => {
    let cancelled = false
    fetchMarketOpportunitySettings()
      .then((data) => !cancelled && setDestinationMarkets(data.destination_markets || []))
      .catch(() => !cancelled && setDestinationMarkets([]))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    loadShipmentContext(shipment, origin, destination)
      .then((loaded) => !cancelled && setContext({ loading: false, error: '', ...loaded }))
      .catch((err) => !cancelled && setContext({ loading: false, error: err?.message || 'Could not load the costs.', countries: null, prices: null, multipliers: null }))
    return () => {
      cancelled = true
    }
  }, [origin, destination])

  const allocated = shipment.items.reduce((sum, item) => sum + item.kg, 0)
  // each product's cost, market level and suggested sale price (shared with the route table: shipmentFinance.js)
  const finance = useMemo(() => financeForShipment(shipment, context, airfarePerKg, destinationMarkets), [shipment, context, airfarePerKg, destinationMarkets])
  const { ddpTotal, saleTotal } = finance
  const costs = useMemo(() => new Map([...finance.items].map(([item, entry]) => [item, entry.cost])), [finance])
  const levels = useMemo(() => new Map([...finance.items].map(([item, entry]) => [item, entry.level])), [finance])
  const sales = useMemo(() => new Map([...finance.items].map(([item, entry]) => [item, entry.sale])), [finance])

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
        {saleTotal != null && ` · sale total ${usd0(saleTotal)}`}
      </div>
      {context.error && <div className="shipment-panel__error">{context.error}</div>}
      <div className="revenue-streams-view__shipment-cards">
        {shipment.items.map((item) => {
          const cost = costs.get(item)
          const level = levels.get(item)
          const sale = sales.get(item)
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
              {item.manual && <span className="shipment-panel__manual-pill">manual</span>}
              <span className="revenue-streams-view__shipment-kg">{kgText(item.kg)}</span>
              <span className="shipment-panel__money">
                <span className="shipment-panel__cost" title="Product cost (DDP total)">
                  {context.loading ? '…' : usd0(cost.ddp)}
                </span>
                <span className="shipment-panel__sale" title={sale?.note ? `Suggested sale price — ${sale.note}` : 'Suggested sale price: sell price per kg x weight'}>
                  {context.loading ? '…' : usd0(sale?.total)}
                </span>
              </span>
              <span
                className="revenue-streams-view__shipment-meta"
                title={
                  level?.noMatch
                    ? 'No match in the target market: a niche market product'
                    : level?.share == null
                    ? 'Needs the DDP price and the target price'
                    : !level.configured
                      ? `DDP is ${level.share.toFixed(1)}% of the target price. Set the ranges in Settings ▸ Market Opportunity settings ▸ Destination Market.`
                      : `DDP is ${level.share.toFixed(1)}% of the target price${level.level ? '' : ' — outside every Destination Market range'}`
                }
              >
                Market level: {context.loading ? '…' : (level?.level ?? '—')}
              </span>
              <button type="button" className="shipment-panel__details-btn" onClick={() => setDetailKey(`${item.product_name}|${item.hs_code ?? ''}`)}>
                Details
              </button>
            </div>
          )
        })}
      </div>
      {detailItem && (
        <ProductDetails
          key={detailKey}
          item={detailItem}
          cost={costs.get(detailItem)}
          sale={sales.get(detailItem)}
          countries={context.countries}
          airfarePerKg={airfarePerKg}
          airfareNote={airfareNote}
          legTitle={legTitle}
          capacityKg={shipment.capacity_kg}
          allocatedKg={allocated}
          onSaveWeight={async (kg) => {
            const items = shipment.items.map((item) => (item === detailItem ? { ...item, kg, manual: true } : item))
            const total = items.reduce((sum, item) => sum + item.kg, 0)
            await onSave({ ...shipment, items: items.map((item) => ({ ...item, share_pct: total ? Math.round((item.kg / total) * 1000) / 10 : 0 })) })
          }}
          onOpenMarketOpportunities={() => openMarketOpportunities(detailItem.product_name)}
          onClose={() => setDetailKey(null)}
        />
      )}
    </div>
  )
}

function ProductDetails({ item, cost, sale, countries, airfarePerKg, airfareNote, legTitle, capacityKg, allocatedKg, onSaveWeight, onOpenMarketOpportunities, onClose }) {
  const noMultiplier = cost.multiplier == null
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  // the most this product can be raised to: what is free on the aircraft plus its own weight
  const maxKg = capacityKg != null ? Math.floor(capacityKg - allocatedKg + item.kg) : null
  const startEdit = () => {
    setDraft(String(Math.round(item.kg)))
    setSaveError('')
    setEditing(true)
  }
  const save = async () => {
    const kg = Number(draft)
    if (!Number.isFinite(kg) || kg <= 0) return setSaveError('Enter a weight above 0 kg.')
    if (maxKg != null && kg > maxKg) return setSaveError(`The aircraft only has room for ${maxKg.toLocaleString('en-US')} kg of this product.`)
    setSaving(true)
    setSaveError('')
    try {
      await onSaveWeight(Math.round(kg))
      setEditing(false)
    } catch (err) {
      setSaveError(err?.message || 'Could not save the weight.')
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="shipment-panel__overlay" role="dialog" aria-modal="true" aria-label={`${item.product_name} details`} onClick={onClose}>
      <div className="shipment-panel__modal" onClick={(event) => event.stopPropagation()}>
        <header className="shipment-panel__modal-head">
          <div>
            <span className="shipment-panel__eyebrow">{legTitle} shipment{countries ? ` · ${countries.source} → ${countries.target}` : ''}</span>
            <h3>
              {item.product_name}
              {item.manual && <span className="shipment-panel__manual-pill">manual</span>}
            </h3>
            {editing ? (
              <div className="shipment-panel__edit">
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && save()}
                  aria-label="Assigned weight in kg"
                  autoFocus
                />
                <span>kg</span>
                <button type="button" className="shipment-panel__edit-btn is-primary" onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button type="button" className="shipment-panel__edit-btn" onClick={() => setEditing(false)} disabled={saving}>
                  Cancel
                </button>
              </div>
            ) : (
              <span className="shipment-panel__sub">
                {kgText(item.kg)}{item.hs_code ? ` · HS ${item.hs_code}` : ''}
                <button type="button" className="shipment-panel__edit-btn" onClick={startEdit}>
                  Edit
                </button>
              </span>
            )}
            {saveError && <span className="shipment-panel__warn">{saveError}</span>}
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

        <section className="shipment-panel__section">
          <h4>Suggested sale price</h4>
          <p>Price x kg = {usd(sale?.perKg)}</p>
          <p>
            Total sale price = <strong>{usd(sale?.total)}</strong>
          </p>
          {sale?.perKg == null && sale?.note && <p className="shipment-panel__warn">{sale.note}</p>}
          {sale?.perKg != null && <p className="shipment-panel__sub">{sale.note}</p>}
        </section>
      </div>
    </div>
  )
}

export default ShipmentPanel
