"""Variety Gallery / cross-market variety-matching subsystem.

Anchors every product to a real biological species (scientific_name, via
gbif_client.py + resolver.py), grows a persistent Species/Variety database
one bootstrap at a time (bootstrap.py, cache-first, never repeated for the
same exact variety), and scores cross-country variety matches with a plain,
auditable point system (matching.py) — never AI, never image similarity.

Zero paid-API spend anywhere in this package: GBIF and Wikimedia Commons are
free and keyless; LangSearch is free-tier but keyed (LANGSEARCH_API_KEY) and
degrades to "not configured" with no error when unset; characteristics
extraction from search results is plain keyword matching (characteristics.py),
not a model call of any kind.
"""
