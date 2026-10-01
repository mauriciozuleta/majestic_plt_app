// "CLO — Alfonso Bonilla Aragon International Airport (Cali, FRESH24-Colombia)"
export function branchLabel(branch) {
  const place = [branch.city, branch.companyName].filter(Boolean).join(', ')
  return `${branch.airport ? `${branch.airport} — ` : ''}${branch.name}${place ? ` (${place})` : ''}`
}
