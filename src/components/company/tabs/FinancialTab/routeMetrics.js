// Route calculations ported from AI_FRESH24's Administrator ▸ Logistics ▸
// Air ▸ Routes (operational_functions/routes_utils.py): great-circle
// distance, flight time at the aircraft's cruise speed, and that flight time
// rounded up to the next half hour — called "adjusted flight time" there and
// "block hours" here — times the provider's block-hour cost.

const EARTH_RADIUS_NM = 3440.065

// Haversine great-circle distance in nautical miles, rounded to 2 decimals
// (calculate_distance_haversine).
export function distanceNm(lat1, lon1, lat2, lon2) {
  const toRad = (degrees) => (degrees * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return Math.round(EARTH_RADIUS_NM * c * 100) / 100
}

// Rounded up to the next 0.5 h; a whole number of hours stays as it is
// (calculate_adjusted_flight_time).
export function blockHoursFor(flightTimeHours) {
  const whole = Math.trunc(flightTimeHours)
  const fraction = flightTimeHours - whole
  if (fraction === 0) return whole
  return fraction <= 0.5 ? whole + 0.5 : whole + 1
}

// One leg, origin → destination. Each result is null when the data it needs
// is missing, with the reason in `missing`.
export function computeRouteMetrics({ origin, destination, aircraft, provider }) {
  const missing = []
  const hasCoordinates = (branch) => branch && branch.latitude != null && branch.longitude != null
  if (!hasCoordinates(origin) || !hasCoordinates(destination)) missing.push('airport coordinates')
  const cruise = aircraft?.cruise_speed_kt
  if (!cruise || cruise <= 0) missing.push("the aircraft's cruise speed")
  const hourlyCost = provider?.block_hour_cost
  if (hourlyCost == null) missing.push("the provider's block-hour cost")

  const distance = hasCoordinates(origin) && hasCoordinates(destination)
    ? distanceNm(origin.latitude, origin.longitude, destination.latitude, destination.longitude)
    : null
  const flightTime = distance != null && cruise > 0 ? distance / cruise : null
  const blockHours = flightTime != null ? blockHoursFor(flightTime) : null
  const blockHoursCost = blockHours != null && hourlyCost != null ? blockHours * hourlyCost : null

  return { distanceNm: distance, cruiseSpeedKt: cruise ?? null, flightTimeHours: flightTime, blockHours, blockHourCost: hourlyCost ?? null, blockHoursCost, missing }
}
