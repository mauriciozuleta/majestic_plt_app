import { useEffect, useState } from 'react'
import { fetchRouteFinance } from '../../../../../services/shipments'

// Revenue, COS and Profit of one leg of a route (the three cards of a leg row, and the sums in the route table). Worked out on the SERVER now (backend/shipments/finance.py,
// GET /api/shipments/route-finance); the numbers and the notes equal what this file used to compute (backend/tests/test_shipments_parity.py).
//
// Outbound: Revenue = the suggested sale prices of the products of its built shipment; COS = what those products cost (DDP);
//   Profit = Revenue - COS - the cost of the payload that flies empty ((max payload - kg carried) x the leg's air fare per kg).
// Return:   Revenue = price per kg x the leg's available cargo, where the price per kg is the GSA price x Kg when the return is
//   "full" and the return route's own Price x Kg when it is "compensated"; COS = COS x Kg x available cargo; Profit = Revenue - COS.
// Each figure is null when something it needs is missing (the reason is in `notes`).

// -> { status: 'loading' | 'ready' | 'error', data, error }; data is null while the leg has nothing to work from
export function useLegFinance(route, legKey, { origin, destination, returnBranch, aircraft, provider }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  // everything the figures depend on: a change asks the server again
  const inputs = JSON.stringify([
    route.outbound_shipment,
    route.return_shipment,
    route.return_type,
    route.outbound_leg_cost_pct,
    route.return_leg_cost_pct,
    route.outbound_target_cargo_pct,
    route.return_target_cargo_pct,
    route.return_price_per_kg,
    route.return_cos_per_kg,
    origin?.id,
    destination?.id,
    returnBranch?.id,
    aircraft?.max_payload_kg,
    provider?.block_hour_cost,
  ])

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, status: 'loading' }))
    fetchRouteFinance(route.id, inputs)
      .then((result) => {
        if (cancelled) return
        const leg = result[legKey]
        if (leg.error) setState({ status: 'error', data: null, error: leg.error })
        else setState({ status: 'ready', data: leg.figures, error: '' })
      })
      .catch((err) => !cancelled && setState({ status: 'error', data: null, error: err?.message || 'Could not work out the shipment figures.' }))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `inputs` summarises the route, branches, aircraft and provider
  }, [route.id, legKey, inputs])

  return state
}
