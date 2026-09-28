"""Bootstrap on cache miss (spec section 3) — runs ONLY when
routers/species_gallery.py's cache-first lookup finds no existing
models.Variety row for (scientific_name, variety_name, source_country).
Every external call this module makes (LangSearch, Commons) happens at
most once per distinct variety, ever: a second lookup for the exact same
triple is served straight from the database by the caller, never reaching
this module again.

Composed of three independent sub-steps, each degrading gracefully on its
own rather than blocking the others:
  1. One LangSearch web search -> characteristics.py's keyword extraction
     (no result if LANGSEARCH_API_KEY isn't configured, or the search
     itself returns nothing usable).
  2. Tier A (internal-only) image: best-effort, from the same LangSearch
     result set — a direct-looking image URL among the search results, if
     any turned up. Never a generic/stock substitute.
  3. Tier B (public) image: Wikimedia Commons specifically, via
     commons_client.py — real license/attribution alongside it, or nothing.

The resulting Variety row is always created with confidence_status
'auto-filled - unverified' and created_via 'bootstrap_search' — never
'confirmed' — regardless of how much of steps 1-3 actually found something,
per this feature's own review-queue requirement.

Addition 2: for `category` values in
`openfoodfacts_client.PACKAGED_GOODS_CATEGORIES` (packaged/branded goods —
rice, oil, sugar, chocolate, panela, beans, ... — scoped to Colombia's
'granos_procesados'/USA's 'Grains (Export)' categories, never fresh
produce/meat/seafood/dairy), `bootstrap_variety` below routes to Open Food
Facts (`openfoodfacts_client.search_product`) instead of steps 1-3 —  a
completely separate, real product database rather than a free-text web
search + Commons image lookup, which doesn't fit branded packaged goods
nearly as well as it fits a produce variety. See
`_bootstrap_from_openfoodfacts` below for the branch itself and why its
image is stored as Tier A, never Tier B."""

import json
import re
from typing import Optional

from . import commons_client, langsearch_client, openfoodfacts_client
from .characteristics import extract_characteristics

_IMAGE_URL_RE = re.compile(r'https?://\S+\.(?:jpg|jpeg|png|webp)', re.IGNORECASE)


def _find_tier_a_image(search_results: list[dict]) -> Optional[str]:
    for item in search_results:
        for field_value in (item.get('url'), item.get('text'), item.get('snippet')):
            if not field_value:
                continue
            match = _IMAGE_URL_RE.search(field_value)
            if match:
                return match.group(0)
    return None


def _bootstrap_from_openfoodfacts(variety_name: str, source_country: str) -> dict:
    """Addition 2 branch — packaged/branded goods only (see module
    docstring). Cache-first is already guaranteed by the caller (the
    router never reaches bootstrap_variety for an already-persisted
    triple), so this makes at most one real Open Food Facts search call.

    The image, when a real match is found, is stored as `image_tier_a`,
    NEVER `image_tier_b`: `image_tier_b` is structurally
    Wikimedia-Commons-only with verified, reusable per-image license
    metadata (models.Variety's own docstring; commons_client.py only ever
    accepts an image with a real LicenseShortName). An Open Food Facts
    product photo doesn't carry that same per-image verified-license
    guarantee, so it stays internal-only — the same tier LangSearch's own
    best-effort image already uses, never the structurally public-safe
    one."""
    match = openfoodfacts_client.search_product(variety_name)
    if match is None:
        return {
            'characteristics_json': '{}',
            'image_tier_a': None,
            'image_tier_b': None,
            'image_tier_b_license': None,
            'image_tier_b_attribution': None,
            'image_tier_b_source_url': None,
            'bootstrap_note': (
                f'Open Food Facts: no real match found for "{variety_name}" ({source_country}) — '
                'left empty, never substituted with a generic search image.'
            ),
        }
    characteristics = {
        'package_size': match['package_size'],
        'brand': match['brand'],
        'off_category': match['off_category'],
    }
    return {
        'characteristics_json': json.dumps(characteristics),
        'image_tier_a': match['image_url'],
        'image_tier_b': None,
        'image_tier_b_license': None,
        'image_tier_b_attribution': None,
        'image_tier_b_source_url': None,
        'bootstrap_note': (
            f'Open Food Facts: matched "{match["product_name"] or variety_name}" '
            f'(brand={match["brand"]}, package_size={match["package_size"]}, off_category={match["off_category"]}, '
            f'barcode={match["barcode"]}).'
        ),
    }


def bootstrap_variety(scientific_name: str, common_name: Optional[str], variety_name: str, source_country: str, category: str = 'produce') -> dict:
    """Returns a dict ready to build a models.Variety row from: {
      characteristics: dict, image_tier_a, image_tier_b, image_tier_b_license,
      image_tier_b_attribution, image_tier_b_source_url, bootstrap_note }.
    Never raises — every sub-step catches its own failures (see
    langsearch_client.web_search / commons_client.find_variety_image), so a
    bootstrap always produces SOMETHING persistable, even if every field in
    it ends up null/empty because nothing could be found or LangSearch
    isn't configured.

    `category` is the hook point for Addition 2: a packaged/branded-goods
    category (openfoodfacts_client.PACKAGED_GOODS_CATEGORIES) routes to
    Open Food Facts entirely instead of steps 1-3 below — never both."""
    if category in openfoodfacts_client.PACKAGED_GOODS_CATEGORIES:
        return _bootstrap_from_openfoodfacts(variety_name, source_country)

    species_label = common_name or scientific_name
    notes = []

    # Step 1: one LangSearch web search -> characteristics
    characteristics = {}
    tier_a_image = None
    if not langsearch_client.is_configured():
        notes.append('LangSearch not configured (LANGSEARCH_API_KEY unset) — characteristics/Tier A image skipped.')
    else:
        query = f'{variety_name} {source_country} {species_label} variety characteristics'
        search = langsearch_client.web_search(query)
        if search is None:
            notes.append('LangSearch web search failed or returned nothing usable.')
        else:
            characteristics = extract_characteristics(search['results'], category=category)
            filled = [k for k, v in characteristics.items() if v is not None]
            notes.append(f'LangSearch search ran; characteristics filled from keyword matches: {filled or "none"}.')
            tier_a_image = _find_tier_a_image(search['results'])
            notes.append(f'Tier A image {"found" if tier_a_image else "not found"} among search results.')

    # Step 3: Wikimedia Commons, specifically, for the Tier B public image.
    # Query construction (species-context bias + fallback) and the
    # art/painting-exclusion hard gate both live in commons_client.py now —
    # see its own module docstring for the real, empirically-tested case
    # behind both.
    commons_result = commons_client.find_variety_image(variety_name, species_label)
    if commons_result is None:
        notes.append('Wikimedia Commons: no licensed image found for this variety.')
    else:
        notes.append(f"Wikimedia Commons: found image under {commons_result['license']}.")

    return {
        'characteristics_json': json.dumps(characteristics),
        'image_tier_a': tier_a_image,
        'image_tier_b': commons_result['url'] if commons_result else None,
        'image_tier_b_license': commons_result['license'] if commons_result else None,
        'image_tier_b_attribution': commons_result['attribution'] if commons_result else None,
        'image_tier_b_source_url': commons_result['source_url'] if commons_result else None,
        'bootstrap_note': ' '.join(notes),
    }
