// "CLO — Alfonso Bonilla Aragon International Airport (Cali, FRESH24-Colombia)"
export function branchLabel(branch) {
  const place = [branch.city, branch.companyName].filter(Boolean).join(', ')
  return `${branch.airport ? `${branch.airport} — ` : ''}${branch.name}${place ? ` (${place})` : ''}`
}

// "B737-8F (737-800BCF)"
export function aircraftLabel(aircraft) {
  return aircraft ? `${aircraft.short_name} (${aircraft.model})` : null
}

export const RETURN_TYPES = [
  { value: 'full', label: 'Full' },
  { value: 'compensated', label: 'Compensated' },
]

// "MDE" — the branch's IATA code (its name when it has none); the full
// branchLabel() goes in a tooltip.
export function branchCode(branch) {
  return branch.airport || branch.name
}
