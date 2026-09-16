// Mirrors backend/risk_scoring.py — keep both in sync if the scale changes.

export const LEVELS = ['VL', 'L', 'M', 'H', 'VH']
export const LEVEL_LABEL = { VL: 'Very low', L: 'Low', M: 'Medium', H: 'High', VH: 'Very high' }
export const SCALE_UP = { VL: 1, L: 2, M: 3, H: 4, VH: 5 }
// Cost is inverted on purpose: a cheap mechanism (VL cost) scores high, an
// expensive one (VH cost) scores low — cost is the one axis where "less"
// is the good outcome.
export const SCALE_COST = { VL: 5, L: 4, M: 3, H: 2, VH: 1 }

// Placeholder tiering, pending a proper management-scorecard method — net
// ranges roughly -4..+4. Only risks at or above this threshold count as
// "well managed" enough to name in an investor-facing Generate Plan.
export const WELL_MANAGED_THRESHOLD = 1

export function exposureScore(risk) {
  return (SCALE_UP[risk.probability] + SCALE_UP[risk.impact]) / 2
}

export function mechanismScore(mechanism) {
  return (SCALE_UP[mechanism.capacity] + SCALE_COST[mechanism.cost]) / 2
}

export function mitigationScore(mechanisms) {
  if (!mechanisms || mechanisms.length === 0) return 0
  return mechanisms.reduce((sum, m) => sum + mechanismScore(m), 0) / mechanisms.length
}

export function netScore(risk, mechanisms) {
  if (!mechanisms || mechanisms.length === 0) return 0
  return mitigationScore(mechanisms) - exposureScore(risk)
}

export function managementTier(net, hasMechanisms) {
  if (!hasMechanisms) return 'unmanaged'
  if (net >= WELL_MANAGED_THRESHOLD) return 'well_managed'
  if (net >= 0) return 'partially_managed'
  return 'unmanaged'
}

export const TIER_LABEL = {
  unmanaged: 'Unmanaged',
  partially_managed: 'Partially managed',
  well_managed: 'Well managed',
}

export const TIER_COLOR = {
  unmanaged: '#FCA5A5',
  partially_managed: '#F2C77D',
  well_managed: '#9FE7C6',
}
