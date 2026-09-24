"""Orchestrates Tiers 3-4 of the Colombia product-name translation fallback
chain, for names the static dictionary (Tier 1, productTranslations.js) and
the confirmed-override fuzzy match (Tier 2, both client-side — see that
file) both missed. Never calls Claude: local_model.py (a dedicated MT
model) is tried first, then web_search.py (a plain search API), stopping
at whichever produces a usable result first. Every result is unverified by
definition — see models.ProductTranslationSuggestion — a human confirms or
rejects it via the /market-analysis/colombia/translation-suggestions
endpoints (backend/routers/price_comparison.py) before it can ever reach
the permanent dictionary."""

from . import local_model, web_search

LOCAL_MODEL_TIER = 3
WEB_SEARCH_TIER = 4


def resolve_one(name_es: str) -> dict | None:
    """{"suggestion_en", "tier", "confidence"} for one product name, or
    None if neither tier produced anything usable."""
    translated = local_model.translate(name_es)
    if translated:
        return {'suggestion_en': translated, 'tier': LOCAL_MODEL_TIER, 'confidence': None}

    searched = web_search.search_translation(name_es)
    if searched:
        return {'suggestion_en': searched, 'tier': WEB_SEARCH_TIER, 'confidence': 'lower confidence than the local model'}

    return None


def resolve_many(names_es: list[str]) -> dict[str, dict | None]:
    """One resolve_one call per distinct name — names_es may contain
    duplicates (several rows sharing the same untranslated product name);
    each is only ever resolved once."""
    return {name: resolve_one(name) for name in dict.fromkeys(names_es)}
