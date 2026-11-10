"""Which target product is the same product as a source product, in four tiers (a port of the matching of src/services/marketOpportunities.js):
  1. an exact (or translated-exact) name, or a curated override of the pair (data/cross_country_overrides.json)
  2. — the same, listed first because both are decided by the name
  3. an AI judge (Claude, cached by the product-matches module) over the target products in the source product's HS chapter (plus the ones the classifier could not code;
     every target product when the source has no code) — labelled 'hs_code' when they also share the exact HS code, 'ai_match' otherwise
  4. only when the AI judge cannot run: every target product sharing the exact HS code ('hs_code')
A shared HS code is a customs category, not product identity (every USA chicken cut shares 020713 with Jamaica's necks, feet and backs), which is why the AI judge exists."""

import json
from pathlib import Path

OVERRIDES_FILE = Path(__file__).resolve().parent / 'data' / 'cross_country_overrides.json'


def load_overrides() -> dict:
    try:
        return json.loads(OVERRIDES_FILE.read_text(encoding='utf-8')).get('overrides', {})
    except (OSError, ValueError):
        return {}


def lookup_override(source_country: str, target_country: str, normalized_source_name: str) -> str | None:
    return (load_overrides().get(f'{source_country}|{target_country}') or {}).get(normalized_source_name) or None


def name_pairs(source_country: str, target_country: str, source_products: list[dict], target_products: list[dict]) -> tuple[list[dict], dict]:
    """(pairs, paired_by_source) — tiers 1/2. `paired_by_source` maps a source product (by identity) to the target names it was already paired with, so the AI never
    re-emits those."""
    target_by_name = {product['matchName']: product for product in target_products}  # a later product with the same match name wins, as the Map did
    pairs, paired = [], {}
    for sp in source_products:
        override_name = lookup_override(source_country, target_country, sp['matchName'])
        match = (override_name and target_by_name.get(override_name)) or target_by_name.get(sp['matchName'])
        if not match:
            continue
        tier = 'curated_override' if override_name else 'translated_exact' if sp.get('translated') else 'exact'
        pairs.append({'sp': sp, 'tp': match, 'matchTier': tier, 'targetCountry': target_country})
        paired[id(sp)] = {match['displayName'].strip()}
    return pairs, paired


def _undefined(value):
    """JavaScript printed a missing value as 'undefined'; the AI cache is keyed on that text, so it is kept for products without a category or unit."""
    return 'undefined' if value is None else value


def ai_match_key(source_country: str, product: dict) -> str:
    return f"{source_country}|{_undefined(product.get('category'))}|{product['displayName']}".lower()


def ai_match_description(source_country: str, product: dict) -> str:
    return f"\"{product['displayName']}\" — category: {_undefined(product.get('category'))}; priced {_undefined(product.get('priceUnit'))}; source: {product['sourceLabel']} ({source_country})"


def resolve_ai_matches(source_country: str, target_country: str, sources: list[dict], paired: dict, target_products: list[dict], match_fn) -> dict:
    """{pairs, unjudged, error}. `match_fn(target_country, groups)` is the AI judge: groups = [{candidates: [names], sources: [{key, description}]}] ->
    {results: {key: {matches, note}}, errors: [..]}. A source whose batch failed is left in `unjudged` for the caller's fallback."""
    targets_by_name: dict[str, list[dict]] = {}
    for tp in target_products:
        targets_by_name.setdefault(tp['displayName'].strip(), []).append(tp)
    # a target product the classifier could not code could belong to any chapter, so it joins every chapter's candidate list rather than being invisible to coded sources
    names_by_chapter: dict[str, list[str]] = {}
    uncoded: list[str] = []
    for name, products in targets_by_name.items():
        chapter = (products[0].get('hsCode') or '')[:2]
        if not chapter:
            uncoded.append(name)
        else:
            names_by_chapter.setdefault(chapter, []).append(name)

    groups: dict[str, dict] = {}
    for sp in sources:
        chapter = (sp.get('hsCode') or '')[:2] or None
        candidates = [*names_by_chapter.get(chapter, []), *uncoded] if chapter else list(targets_by_name)
        if not candidates:
            continue
        group = groups.setdefault(chapter or 'unclassified', {'candidates': candidates, 'sources': []})
        group['sources'].append({'key': ai_match_key(source_country, sp), 'description': ai_match_description(source_country, sp)})
    if not groups:
        return {'pairs': [], 'unjudged': [], 'error': None}

    answer = match_fn(target_country, list(groups.values()))
    results, errors = answer.get('results') or {}, answer.get('errors') or []
    pairs, unjudged = [], []
    for sp in sources:
        result = results.get(ai_match_key(source_country, sp))
        if not result:
            unjudged.append(sp)  # part of a batch whose AI call failed — handled by the caller's fallback
            continue
        already = paired.get(id(sp), set())
        for name in result.get('matches') or []:
            if name in already:
                continue
            for tp in targets_by_name.get(name, []):
                tier = 'hs_code' if sp.get('hsCode') and tp.get('hsCode') == sp['hsCode'] else 'ai_match'
                pairs.append({'sp': sp, 'tp': tp, 'matchTier': tier, 'targetCountry': target_country, 'aiNote': result.get('note')})
    return {'pairs': pairs, 'unjudged': unjudged, 'error': errors[0] if errors else None}


def hs_code_fallback_pairs(sources: list[dict], paired: dict, target_products: list[dict], target_country: str) -> list[dict]:
    """Only when the AI judge cannot run: the old "every target product sharing the exact HS code" pairing, so a comparison still shows what it can."""
    by_code: dict[str, list[dict]] = {}
    for tp in target_products:
        if tp.get('hsCode'):
            by_code.setdefault(tp['hsCode'], []).append(tp)
    pairs = []
    for sp in sources:
        already = paired.get(id(sp), set())
        for tp in by_code.get(sp.get('hsCode'), []):
            if tp['displayName'].strip() in already:
                continue
            pairs.append({'sp': sp, 'tp': tp, 'matchTier': 'hs_code', 'targetCountry': target_country})
    return pairs
