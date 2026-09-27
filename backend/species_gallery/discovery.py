"""Target-country variety DISCOVERY — the real gap `POST /api/species-gallery/match`
(routers/species_gallery.py) had before this module existed: it could only
score varieties that a human had already bootstrapped one at a time via
`/varieties/bootstrap`. Nothing anywhere in this subsystem could turn
"tomato in United States" into a list of real candidate variety NAMES on
its own — `bootstrap.py`'s `bootstrap_variety` only ever bootstraps a
single variety it's ALREADY given the name of.

Same $0/no-AI discipline as the rest of this subsystem (see
VARIETY_GALLERY_METHODOLOGY.md): one LangSearch web search
(`langsearch_client.web_search`), then PLAIN regex/keyword extraction of
candidate names from the result text — never a model call.

How the extraction pattern was actually chosen (empirical, not assumed):
several real query phrasings were run live against LangSearch for
"tomato"/"United States" before writing this. `"common {name} varieties
grown in {country}"` reliably surfaced seed-catalog / grower-reference
pages (reimerseeds.com, gardenguides.com, ...) whose own text consistently
spells a named variety as "<Title Case Words> <common name>" right next to
the species' scientific name, e.g. a real result's text verbatim:

    "72 days. Solanum lycopersicum. Open Pollinated. Bonny Best Tomato.
    This early-maturing plant produces heavy yields of 8 to 10 oz red
    tomatoes. ..."
    "85 days. Solanum lycopersicum. Open Pollinated. Caribe Tomato. ..."

So the extraction regex anchors on exactly that shape: 1-3 capitalized
words immediately followed by the common name (singular or plural). This
also produces some noise (category/listing titles like "Commercial
Production Tomato" or "Verticillium Wilt Resistant Tomatoes" match the same
shape without being a real variety name) — filtered by a small blocklist
below, but not perfectly; by design, EVERY row this module produces is
still persisted as `confidence_status = 'auto-filled - unverified'` and
lands in the same human review queue as every other bootstrap, so a
residual bad candidate is a review-queue item to reject, never a silent
wrong answer shown as fact.

Every candidate is capped (MAX_DISCOVERY_CANDIDATES) and the caller
(routers/species_gallery.py's match_variety) is responsible for excluding
names already cached for this (scientific_name, source_country) pair
before ever calling bootstrap_variety — discovery itself never repeats a
bootstrap for a variety a prior run already found.
"""

import re
from typing import Optional

from . import langsearch_client
from .commodity_dictionary import COMMODITY_TERMS, VERNACULAR_PHRASES

MAX_DISCOVERY_CANDIDATES = 6

# Full phrases that match the extraction pattern's shape but are never
# themselves a real variety name — category/listing language, not a proper
# noun. Compared against the extracted prefix, lowercased, in full.
_GENERIC_PREFIXES = {
    'best', 'top', 'good', 'great', 'commercial', 'popular', 'common',
    'new', 'other', 'most', 'many', 'several', 'various', 'fresh',
    'local', 'domestic', 'field', 'open field', 'high tunnel',
    'commercial production', 'best commercial', 'disease resistant',
}

# A prefix ENDING in one of these words is almost always a descriptive
# category phrase ("Verticillium Wilt Resistant Tomatoes", "Root Knot
# Nematode Resistant Tomato"), not a proper variety name — filtered
# regardless of the rest of the phrase.
_BLOCKED_LAST_WORDS = {
    'resistant', 'tolerant', 'production', 'commercial', 'wilt', 'disease',
    'field', 'tunnel', 'grown', 'organic', 'fresh', 'popular', 'best',
    'top', 'good', 'great', 'other', 'new', 'most', 'many', 'several',
    'various', 'seeds', 'growers', 'research',
}


def _common_name_for_species(scientific_name: str) -> Optional[str]:
    """Best-effort reverse lookup of a plain-English common name for a
    GBIF-confirmed scientific name, from the SAME curated dictionary the
    resolver already trusts (commodity_dictionary.py) — never a guess
    outside that dictionary. Prefers the shortest matching term (e.g.
    "tomato" over "tomatoes") purely for cleaner search-query phrasing;
    matching/scoring never depends on this choice."""
    matches = [term for term, name in COMMODITY_TERMS.items() if name == scientific_name]
    matches += [term for term, name in VERNACULAR_PHRASES.items() if name == scientific_name]
    if not matches:
        return None
    return min(matches, key=len)


def _extract_candidate_names(search_results: list[dict], common_name: str) -> list[str]:
    """Plain regex extraction, no model call — see module docstring for the
    real search-result text this pattern was designed against."""
    singular = common_name[:-1] if common_name.endswith('s') and len(common_name) > 3 else common_name
    pattern = re.compile(r"\b((?:[A-Z][A-Za-z0-9'\-]*\s){1,3})(?i:" + re.escape(singular) + r"s?)\b")

    seen: list[str] = []
    for item in search_results:
        text = ' '.join(part for part in (item.get('name'), item.get('snippet'), item.get('text')) if part)
        for match in pattern.finditer(text):
            prefix = match.group(1).strip()
            if not prefix:
                continue
            prefix_lower = prefix.lower()
            if prefix_lower in _GENERIC_PREFIXES:
                continue
            last_word = prefix_lower.split()[-1]
            if last_word in _BLOCKED_LAST_WORDS:
                continue
            candidate = f'{prefix} {singular.capitalize()}'
            if candidate not in seen:
                seen.append(candidate)
    return seen


def discover_target_varieties(
    scientific_name: str,
    common_name: Optional[str],
    target_country: str,
    existing_variety_names: set[str],
) -> tuple[list[str], str]:
    """Returns (candidate_names, note). `candidate_names` is up to
    MAX_DISCOVERY_CANDIDATES real, extracted (never invented) variety names
    for `scientific_name` grown in `target_country`, excluding anything
    already in `existing_variety_names` (case-insensitive) — an empty list
    is a real, honest result (LangSearch not configured, the search failed,
    or nothing usable was extracted), never padded to look non-empty.
    `note` records what happened, for the same bootstrap_note-style audit
    trail the rest of this subsystem keeps."""
    if not langsearch_client.is_configured():
        return [], 'Discovery skipped: LangSearch not configured (LANGSEARCH_API_KEY unset).'

    label = common_name or _common_name_for_species(scientific_name)
    if not label:
        return [], f'Discovery skipped: no plain-English common name known for {scientific_name} to search/extract with.'

    query = f'common {label} varieties grown in {target_country}'
    search = langsearch_client.web_search(query, count=5)
    if search is None:
        return [], f'Discovery search failed or returned nothing usable for query "{query}".'

    candidates = _extract_candidate_names(search['results'], label)
    existing_lower = {name.lower() for name in existing_variety_names}
    fresh = [c for c in candidates if c.lower() not in existing_lower]
    capped = fresh[:MAX_DISCOVERY_CANDIDATES]
    return capped, f'Discovery search ran ("{query}"); {len(candidates)} candidate name(s) extracted, {len(capped)} new after de-duplication and cap.'
