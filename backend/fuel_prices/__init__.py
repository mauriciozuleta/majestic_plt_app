"""Global aviation fuel price tracker (jet fuel) — an independent module.

Prices are stored per observation with the operator class (scheduled / non_scheduled), the geographic level they describe and where they came from.
`resolve.get_price` answers a place query through a fallback chain and always says which level was used; `stats/` explains price behaviour.
See README.md for sources, terms status and known data gaps.
"""
