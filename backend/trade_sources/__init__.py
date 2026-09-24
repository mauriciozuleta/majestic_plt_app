"""Global Trade Data fallback-source discovery — the automated chain that
decides, ONCE per real country (CountryReferenceCatalog.country_code), at
the moment that country is first added to Commercial Structure, whether
its Global Trade Data view should query UN Comtrade (backend/comtrade/) or
one of the fallback tiers below. See discovery.py for the orchestration,
registry.py for the tier 1/2 per-territory registry, fred_client.py for
tier 3, and robots.py for the shared robots.txt check used before any
newly discovered source is treated as usable.
"""
