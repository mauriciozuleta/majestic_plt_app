import { useEffect, useState } from 'react'
import { fetchRouteFinance } from '../../../../../services/shipments'

// Distance, flight time, block hours and block-hours cost of a route's two legs, worked out on the SERVER (backend/shipments/finance.py compute_route_metrics, through
// GET /api/shipments/route-finance). Hands them to `children({ outbound, return })`; until they arrive each leg has no figures and nothing missing.
const NOTHING_YET = { distanceNm: null, cruiseSpeedKt: null, flightTimeHours: null, blockHours: null, blockHourCost: null, blockHoursCost: null, missing: [] }

export default function RouteLegMetrics({ route, origin, destination, returnBranch, aircraft, provider, children }) {
  const [metrics, setMetrics] = useState({ outbound: NOTHING_YET, return: NOTHING_YET })
  // everything the figures depend on: a change asks the server again
  const inputs = JSON.stringify([
    route.outbound_leg_cost_pct,
    route.return_leg_cost_pct,
    route.return_type,
    [origin?.id, origin?.latitude, origin?.longitude],
    [destination?.id, destination?.latitude, destination?.longitude],
    [returnBranch?.id, returnBranch?.latitude, returnBranch?.longitude],
    aircraft?.cruise_speed_kt,
    provider?.block_hour_cost,
  ])
  useEffect(() => {
    let cancelled = false
    fetchRouteFinance(route.id, inputs)
      .then((result) => !cancelled && setMetrics({ outbound: result.outbound.metrics, return: result.return.metrics }))
      .catch(() => !cancelled && setMetrics({ outbound: NOTHING_YET, return: NOTHING_YET }))
    return () => {
      cancelled = true
    }
  }, [route.id, inputs])
  return children(metrics)
}
