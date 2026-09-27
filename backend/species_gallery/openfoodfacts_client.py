"""Open Food Facts — the second bootstrap source (Addition 2), used ONLY
for packaged/branded goods (rice, oil, sugar, chocolate, panela, beans,
...). Never used for fresh produce/meat/seafood/dairy, which stay on the
existing GBIF + LangSearch + Wikimedia pipeline (bootstrap.py) exactly as
built — this module makes no decision about WHICH varieties reach it,
that's `PACKAGED_GOODS_CATEGORIES` + bootstrap.py's own branch.

Real, live-verified endpoint choice (the spec originally named the older
`/api/v2/search` endpoint — re-verified here, not assumed either way):

  - `GET https://world.openfoodfacts.org/api/v2/search?...` — confirmed
    LIVE, twice, in the same test session, to be genuinely FLAKY for an
    anonymous (keyless) caller: one real request (`categories_tags_en=rice
    &page_size=3`) returned a clean 200 with real product data; a
    near-identical repeat request minutes later returned a real 503 —
    Open Food Facts' own "Page temporarily unavailable... Our services are
    currently experiencing unusually high demand, or the page you
    requested is not available to anonymous users" HTML error page, not a
    client-side param issue. Not safe to depend on as the primary path for
    a keyless, $0 client that must degrade honestly rather than silently
    fail sometimes.
  - `GET https://search.openfoodfacts.org/search?q=<term>&page_size=<n>` —
    Open Food Facts' newer, separate Elasticsearch-backed search
    microservice. Confirmed LIVE, repeatedly, real 200s with real
    structured hits — `code`, `brands` (list), `quantity`
    (e.g. `"2 lbs"`), `categories_tags`, `countries_tags`,
    `image_front_url`/`image_url`, `product_name` all present directly on
    each hit (confirmed by inspecting a real response's keys) — no extra
    per-barcode lookup needed just to get a usable image URL. THIS is the
    endpoint actually used below.
  - `GET https://world.openfoodfacts.org/api/v2/product/{barcode}.json` —
    confirmed live and reliable for a KNOWN barcode (e.g. a real "Supreme
    Rice" 2 lbs product). Not used here — these Colombia/USA packaged
    products won't have a known barcode to look up by — kept only as
    context for why product-lookup and search carry separate published
    rate limits below.

Both endpoints are free and require no API key. Real, explicit throttling
(a sliding-window limiter that SLEEPS to stay under the limit, never a
fire-then-catch-429 retry) — 10 req/min for search, 15 req/min for
product-by-barcode lookups (Open Food Facts' own published limits),
enforced as two independent limiters since they're two different
endpoints/limits (the product limiter is exposed for completeness/future
use even though this module's own search_product() only ever calls the
search endpoint today).

Cache-first discipline is enforced by the CALLER (the router never reaches
bootstrap_variety for an already-persisted (scientific_name, variety_name,
source_country) triple) — this module makes no persistence decisions of
its own, same division of responsibility as langsearch_client.py /
commons_client.py.
"""

import re
import threading
import time
from typing import Optional

import httpx

SEARCH_URL = 'https://search.openfoodfacts.org/search'
TIMEOUT = 15

# Open Food Facts' own User-Agent policy — the same class of failure
# already learned the hard way with Wikimedia Commons in this subsystem
# (see commons_client.py's own comment): a real, identifying string, not a
# default httpx one, on every request.
_USER_AGENT = 'MajesticSoftware-VarietyGallery/1.0 (internal tool; contact: donreymauri@gmail.com)'

# The category values that route a bootstrap to Open Food Facts instead of
# the produce (GBIF+LangSearch+Wikimedia) pipeline. This app's own raw
# taxonomy strings are included directly for robustness —
# 'granos_procesados' is Colombia's own CANONICAL_CATEGORIES key (see
# priceComparisonData.js) and 'Grains (Export)' is USA's raw category
# (backend/usa_sources/grains.py) — but the value actually sent by the
# frontend today is the canonical 'packaged_goods'
# (SpeciesGalleryPanel.jsx maps a selected product's own category to this
# before calling bootstrap/match). Why a mapping is needed at all, rather
# than passing 'granos_procesados' straight through: confirmed live by
# reading productPortfolio.js that buildProductPortfolio() only exposes the
# already-resolved DISPLAY LABEL by the time a product reaches the Gallery
# ('Grains & Processed' for Colombia, 'Grains (Export)' for USA — see
# categoryInfo()/CATEGORY_CODES there), not the raw taxonomy key — so
# 'Grains & Processed' (Colombia's own label) is included here too.
PACKAGED_GOODS_CATEGORIES = {
    'packaged_goods',
    'granos_procesados',
    'Grains & Processed',
    'Grains (Export)',
}


class _RateLimiter:
    """Sliding-window limiter: `acquire()` blocks (sleeps) the caller until
    a call is genuinely safe to make under `max_calls` per trailing
    `window_seconds` — real throttling, never firing a request and reacting
    to a 429 after the fact."""

    def __init__(self, max_calls: int, window_seconds: float = 60.0):
        self._max_calls = max_calls
        self._window = window_seconds
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t <= self._window]
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
                sleep_for = self._window - (now - self._calls[0]) + 0.05
            time.sleep(max(sleep_for, 0.05))


# Open Food Facts' own published limits: 10 req/min for search, 15 req/min
# for product-by-barcode lookups.
_search_limiter = _RateLimiter(max_calls=10, window_seconds=60.0)
_product_limiter = _RateLimiter(max_calls=15, window_seconds=60.0)  # reserved for a future barcode-lookup path


# Generic commodity/descriptor words that appear across countless
# unrelated real Open Food Facts products — a query token matching ONLY
# words in this list can never, by itself, establish a genuine match.
# Confirmed live this matters, not hypothetical: an early version of this
# matcher (OR-logic over every token > 2 chars) matched "Regular Rice"
# (a Colombian wholesale-market generic commodity name, no real brand
# behind it) to a real hit whose own brand field is literally "Regular" —
# a JIK-brand bleach product, entirely unrelated to rice, matched purely
# because both query tokens happen to be individually common words. Real
# distinctive tokens (a brand/place/variety name — "Oryzica", "Cargamanto",
# "Nima", "Pastusa", ...) are required below before any hit is ever
# accepted; a query with no such token (e.g. a plain, unbranded "Regular
# Rice"/"Packaged Sugar"/"Chickpeas" wholesale-market entry) returns None
# immediately — an honest "nothing specific enough to search by", never a
# coincidental generic-word accept.
_GENERIC_COMMODITY_WORDS = {
    'rice', 'oil', 'oils', 'sugar', 'bean', 'beans', 'corn', 'wheat', 'soy',
    'soybean', 'soybeans', 'chocolate', 'panela', 'coffee', 'chickpea',
    'chickpeas', 'lentil', 'lentils', 'grain', 'grains', 'granos',
    'procesados', 'processed', 'regular', 'packaged', 'vegetable',
    'vegetables', 'drinking', 'sweet', 'style', 'brand', 'bottle', 'jug',
    'gallon', 'pound', 'pounds', 'export', 'bulk', 'yellow', 'white',
    'common', 'soup', 'dulce', 'the', 'and', 'for', 'with',
}


def _distinctive_terms(query_terms: list[str]) -> list[str]:
    return [t for t in query_terms if t not in _GENERIC_COMMODITY_WORDS and not t[0].isdigit()]


def _off_category_label(categories_tags: list) -> Optional[str]:
    if not categories_tags:
        return None
    # The last tag is consistently the most specific in a real response
    # (e.g. "en:long-grain-rices" after "en:rices" after "en:cereal-grains")
    # — a reasonable single "category" characteristic to store, per spec.
    return categories_tags[-1].split(':', 1)[-1].replace('-', ' ')


def search_product(query: str, page_size: int = 5) -> Optional[dict]:
    """Searches Open Food Facts (the live search microservice, see module
    docstring) for `query` and returns the first hit whose own product
    name/brand/category text genuinely contains a real query term — never
    just the top-ranked hit regardless of relevance. This matters
    concretely: this index is dominated by European (mostly French)
    products, so an unrelated top hit outranking a real Colombian/US brand
    on generic commodity terms is a real, observed outcome, not a
    hypothetical. Returns
    {'product_name', 'brand', 'package_size', 'off_category', 'image_url',
    'barcode'} on a genuine match, or None — a real, honest "no match"
    result (e.g. a small regional Colombian brand this index skews away
    from covering, or a query with no distinctive term at all — see
    `_distinctive_terms`), never a generic/stock image substituted in its
    place.
    """
    # len > 2 skips noise tokens ("de", "el", ...) that would otherwise
    # match almost anything and defeat the relevance check below.
    query_terms = [t for t in re.split(r'\W+', query.lower()) if len(t) > 2]
    distinctive_terms = _distinctive_terms(query_terms)
    if not distinctive_terms:
        # Nothing in this query is specific enough to safely anchor a
        # match on (every token is a generic commodity/descriptor word) —
        # skip the call entirely rather than risk a coincidental
        # generic-word accept (see _GENERIC_COMMODITY_WORDS).
        return None

    _search_limiter.acquire()
    try:
        response = httpx.get(
            SEARCH_URL,
            params={'q': query, 'page_size': page_size},
            headers={'User-Agent': _USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    hits = data.get('hits') or []
    for hit in hits:
        product_name = hit.get('product_name') or ''
        brands = hit.get('brands') or []
        brand_text = ' '.join(brands) if isinstance(brands, list) else str(brands)
        categories_tags = hit.get('categories_tags') or []
        haystack = f'{product_name} {brand_text} {" ".join(categories_tags)}'.lower()
        if not any(term in haystack for term in distinctive_terms):
            continue  # a real hit, but not genuinely about this query — try the next one
        return {
            'product_name': product_name or None,
            'brand': brand_text or None,
            'package_size': hit.get('quantity') or None,
            'off_category': _off_category_label(categories_tags),
            'image_url': hit.get('image_front_url') or hit.get('image_url'),
            'barcode': hit.get('code'),
        }
    return None
