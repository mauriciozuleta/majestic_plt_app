import { useEffect, useMemo, useState } from 'react'
import { fetchMarketOpportunitySettings } from '../../../../../services/marketOpportunitySettings'
import { legPricePerKg } from '../routeMetrics'
import { financeForShipment, loadShipmentContext } from './shipmentFinance'

// Revenue, COS and Profit of one leg of a route (the three cards of a leg row, and the sums in the route table).
//
// Outbound: Revenue = the suggested sale prices of the products of its built shipment; COS = what those products cost (DDP);
//   Profit = Revenue - COS - the cost of the payload that flies empty ((max payload - kg carried) x the leg's air fare per kg).
// Return:   Revenue = price per kg x the leg's available cargo, where the price per kg is the GSA price x Kg when the return is
//   "full" and the return route's own Price x Kg when it is "compensated"; COS = COS x Kg x available cargo; Profit = Revenue - COS.
// Each figure is null when something it needs is missing (the reason is in `notes`).

const dash = (note) => ({ revenue: null, cos: null, profit: null, notes: { revenue: note, cos: note, profit: note } })

// Return leg: no loading involved. `context` = { origin, destination, returnBranch, aircraft, provider } of the route.
export function returnLegFinance(route, context) {
  if (!route.return_type) return dash('Select the type of return')
  const capacityKg = context.aircraft?.max_payload_kg ?? null
  const targetPct = route.return_target_cargo_pct
  const missing = []
  if (targetPct == null) missing.push('the return target cargo %')
  if (!capacityKg) missing.push("the aircraft's max payload")
  const availableKg = targetPct != null && capacityKg ? (targetPct / 100) * capacityKg : null
  const full = route.return_type === 'full'
  const pricePerKg = full ? route.return_price_per_kg : legPricePerKg(route, 'return', context).value
  const priceNote = full ? 'Enter the GSA price x Kg (Add GSA terms)' : legPricePerKg(route, 'return', context).note || 'Needs the return route Price x Kg'
  const revenue = pricePerKg != null && availableKg != null ? pricePerKg * availableKg : null
  const cos = route.return_cos_per_kg != null && availableKg != null ? route.return_cos_per_kg * availableKg : null
  const profit = revenue != null && cos != null ? revenue - cos : null
  const needs = (list) => `Needs ${list.join(' and ')}`
  return {
    revenue,
    cos,
    profit,
    availableKg,
    notes: {
      revenue:
        revenue != null
          ? `${full ? 'GSA price' : 'Return route price'} x Kg ${pricePerKg} x ${Math.round(availableKg).toLocaleString('en-US')} kg available cargo`
          : needs([...(pricePerKg == null ? [priceNote] : []), ...missing]),
      cos:
        cos != null
          ? `COS x Kg ${route.return_cos_per_kg} x ${Math.round(availableKg).toLocaleString('en-US')} kg available cargo`
          : needs([...(route.return_cos_per_kg == null ? ['the COS x Kg (Add COS)'] : []), ...missing]),
      profit: profit != null ? 'Revenue − COS' : 'Needs the revenue and the COS',
    },
  }
}

// -> { status: 'loading' | 'ready' | 'error', data, error }; data is null while the leg has nothing to work from
export function useLegFinance(route, legKey, { origin, destination, returnBranch, aircraft, provider }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  const returnData = useMemo(
    () => (legKey === 'return' ? returnLegFinance(route, { origin, destination, returnBranch, aircraft, provider }) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the route and the objects it depends on, below
    [legKey, JSON.stringify([route.return_type, route.return_target_cargo_pct, route.return_price_per_kg, route.return_cos_per_kg, route.outbound_leg_cost_pct, route.return_leg_cost_pct, route.outbound_target_cargo_pct]), origin?.id, destination?.id, returnBranch?.id, aircraft?.max_payload_kg, provider?.block_hour_cost],
  )
  // everything the outbound figures depend on
  const inputs = JSON.stringify([
    route.outbound_shipment,
    route.return_type,
    route.outbound_leg_cost_pct,
    route.return_leg_cost_pct,
    route.outbound_target_cargo_pct,
    route.return_target_cargo_pct,
    origin?.id,
    destination?.id,
    returnBranch?.id,
    aircraft?.max_payload_kg,
    provider?.block_hour_cost,
  ])

  useEffect(() => {
    if (legKey !== 'outbound') return undefined
    const shipment = route.outbound_shipment
    if (!shipment) {
      setState({ status: 'ready', data: null, error: '' })
      return undefined
    }
    let cancelled = false
    setState((prev) => ({ ...prev, status: 'loading' }))
    Promise.all([fetchMarketOpportunitySettings().catch(() => ({ destination_markets: [] })), loadShipmentContext(shipment, origin, destination)])
      .then(([settings, loaded]) => {
        const airfare = legPricePerKg(route, 'outbound', { origin, destination, returnBranch, aircraft, provider }).value
        const finance = financeForShipment(shipment, loaded, airfare, settings.destination_markets || [])
        const carried = shipment.items.reduce((sum, item) => sum + item.kg, 0)
        const unusedKg = Math.max(0, (aircraft?.max_payload_kg ?? shipment.capacity_kg) - carried)
        const unusedCost = airfare != null ? unusedKg * airfare : null
        const revenue = finance.saleTotal
        const cos = finance.ddpTotal
        const profit = revenue != null && cos != null && unusedCost != null ? revenue - cos - unusedCost : null
        const waiting = 'Needs every product’s cost and sale price, and the route’s air fare'
        const data = {
          revenue,
          cos,
          profit,
          unusedKg,
          unusedCost,
          notes: {
            revenue: revenue != null ? 'The suggested sale prices of the shipment’s products' : waiting,
            cos: cos != null ? 'What the shipment’s products cost (DDP)' : waiting,
            profit:
              profit != null
                ? `Revenue − COS${unusedKg >= 1 ? ` − ${Math.round(unusedCost).toLocaleString('en-US')} USD for the ${Math.round(unusedKg).toLocaleString('en-US')} kg of payload flying empty` : ''}`
                : waiting,
          },
        }
        if (!cancelled) setState({ status: 'ready', data, error: '' })
      })
      .catch((err) => !cancelled && setState({ status: 'error', data: null, error: err?.message || 'Could not work out the shipment figures.' }))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `inputs` summarises the route, branches, aircraft and provider
  }, [legKey, inputs])

  if (legKey === 'return') return { status: 'ready', data: returnData, error: '' }
  return state
}
