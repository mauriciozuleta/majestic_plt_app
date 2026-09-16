"""Risk Analysis scoring — the same 5-point scale and formulas the frontend
uses (see riskScoring.js), duplicated here only because the Generate Plan
endpoint needs to decide server-side which risks qualify as "well managed"
before it will write about them. Keep both in sync if the scale changes.
"""

SCALE_UP = {'VL': 1, 'L': 2, 'M': 3, 'H': 4, 'VH': 5}
# Cost is inverted on purpose: a cheap mechanism (VL cost) scores high, an
# expensive one (VH cost) scores low — cost is the one axis where "less" is
# the good outcome.
SCALE_COST = {'VL': 5, 'L': 4, 'M': 3, 'H': 2, 'VH': 1}

# Placeholder tiering, pending the user's own management-scorecard method —
# net = mitigation - exposure, ranges roughly -4..+4. Only risks at or above
# this threshold are considered "well managed" enough to name in an
# investor-facing plan.
WELL_MANAGED_THRESHOLD = 1.0


def exposure_score(risk) -> float:
    return (SCALE_UP.get(risk.probability, 3) + SCALE_UP.get(risk.impact, 3)) / 2


def mechanism_score(mechanism) -> float:
    return (SCALE_UP.get(mechanism.capacity, 3) + SCALE_COST.get(mechanism.cost, 3)) / 2


def mitigation_score(mechanisms) -> float:
    if not mechanisms:
        return 0.0
    return sum(mechanism_score(m) for m in mechanisms) / len(mechanisms)


def net_score(risk, mechanisms) -> float:
    if not mechanisms:
        return 0.0
    return mitigation_score(mechanisms) - exposure_score(risk)


def management_tier(net: float, has_mechanisms: bool) -> str:
    if not has_mechanisms:
        return 'unmanaged'
    if net >= WELL_MANAGED_THRESHOLD:
        return 'well_managed'
    if net >= 0:
        return 'partially_managed'
    return 'unmanaged'


def is_well_managed(risk, mechanisms) -> bool:
    return management_tier(net_score(risk, mechanisms), bool(mechanisms)) == 'well_managed'
