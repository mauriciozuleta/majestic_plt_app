"""Wikimedia Commons image sourcing — the Variety Gallery's Tier B (public)
image path (spec section 2/3.3). Free, keyless, confirmed live. Confirmed
live BEFORE this client existed that a request with no User-Agent header
gets a silent 403 (Wikimedia's API etiquette requires one identifying the
calling application: https://meta.wikimedia.org/wiki/User-Agent_policy) —
`_USER_AGENT` below sets a real, identifying one on every request so that
failure mode can't recur.

Returns a real image URL + its real license/attribution (from the file's
own extmetadata — LicenseShortName, Attribution/Artist with HTML tags
stripped) or nothing at all — Tier B is never backfilled with a Tier A or
generic image when Commons genuinely has nothing for a variety, per this
feature's own structural Tier A/B separation rule.

Real bug found and fixed in this pass: a real bootstrap ("Grey" Orange /
Colombia) picked `File:Aleksander_Gierymski_-_Jewish_woman_selling_oranges_
-_Google_Art_Project.jpg` as its Tier B image — an 1880s painting, not a
photo of the fruit. Confirmed live why the existing filters didn't catch
it: `filetype:bitmap` only restricts container format (a scanned painting
saved as JPEG still matches it), and the file's own MIME type
(`image/jpeg`) is identical to a real photo's — neither is a usable
art-vs-photo signal on its own. What IS checkable and unambiguous: the
file's real Commons categories. The Gierymski file's own categories
include `Category:Artworks digital representation of 2D work`,
`Category:Featured pictures of paintings from Poland`,
`Category:Google Art Project works by Aleksander Gierymski`,
`Category:PD-Art (PD-old-auto-expired)` — confirmed live via
`action=query&prop=categories`. `_ART_EXCLUSION_KEYWORDS` below is a hard
gate built from real category text seen across several more real Commons
food-image searches in this pass ("orange fruit painting", "apple fruit
still life", ...), not just the one case: real, repeatedly-seen markers
like `still life`, `watercolor`, `museum of art`, `pd-art`, `postage
stamp` all showed up sourcing real fruit-adjacent search results that were
not photos of the fruit itself. `portrait` was deliberately NOT included
despite showing up in the original brief's own suggested list — confirmed
live that `Category:Portrait orientation` (a photo ASPECT RATIO tag, one
of Commons' most common categories on completely ordinary photos) would
false-positive on a bare substring match; a real art-portrait category is
already caught by `painting`/`artwork`/`google art project` instead.

Query-side bias (also real, also empirically tested, not assumed): biasing
the search query toward species context
(`f'{variety_name} {species_label} fruit photograph'`) was tried live
against every real variety already in this app's own database ("Grey"
Orange/Citrus sinensis, "Kidney" Tomato/Solanum lycopersicum, Roma Tomato,
Tomate Chonto, Caribe Tomato, all with their real scientific binomial) —
confirmed live it returns ZERO raw search hits in every one of those real
cases; CirrusSearch's relevance engine doesn't degrade gracefully to a
worse-ranked result when too many required-ish terms are combined, it
returns nothing at all. So `find_variety_image` tries that biased query
first (in case it helps for some future variety/species pairing), then
falls back to the original, narrower query (no bias words) when the
biased one returns nothing — which is what actually still returns
candidates in every real case tested. The category-exclusion filter runs
identically against whichever stage's candidates are being evaluated, and
is the fix that actually keeps a bad candidate like the Gierymski painting
from being accepted (confirmed live: with the category filter in place,
re-running against "Grey" Orange's real fallback-stage candidates
correctly skips the Gierymski painting and accepts the next candidate that
passes — a real, licensed photo of oranges). Reported honestly, matching
this subsystem's own "confirmed live, here's what actually works" style
rather than assuming the query-bias half of the fix pulls its own weight —
right now the category filter is doing effectively all of the real
preventive work.
"""

import re
from typing import Optional

import httpx

API_URL = 'https://commons.wikimedia.org/w/api.php'
TIMEOUT = 15
# Wikimedia's own User-Agent policy requires a real, identifying string —
# confirmed live that omitting this produces a 403 with no other clue why.
_USER_AGENT = 'MajesticSoftware-VarietyGallery/1.0 (internal tool; contact: donreymauri@gmail.com)'

_TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _TAG_RE.sub('', value).strip() or None


# Commons' File namespace (6) includes PDFs, SVG diagrams, audio and other
# non-photo files alongside real photos — confirmed live that a plain
# srsearch for a produce variety name can rank an entirely unrelated PDF
# (an EU Official Journal document, in one real test) above any actual
# photo. Restricted to real raster photo formats only, both in the search
# query itself (CirrusSearch's `filetype:` keyword) and, as a second real
# check, on the fetched file's own reported MIME type before it's ever
# accepted — belt and suspenders, since `filetype:` narrows the search
# results but this app never trusts a single signal alone for something
# that ends up in a public response.
_ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

# Hard gate (module docstring above has the full real-case investigation):
# a Commons file's own categories are the one signal that reliably
# distinguishes a painting/illustration/artwork reproduction from an actual
# photograph, when `filetype:bitmap` and MIME type both can't. Matched as a
# case-insensitive substring against each of the file's real category
# titles — deliberately NOT anchored to word boundaries (a real category is
# always several words, e.g. "Category:Featured pictures of paintings from
# Poland"), and deliberately excludes bare `portrait` (see docstring: real
# false-positive risk against `Category:Portrait orientation`).
_ART_EXCLUSION_KEYWORDS = (
    'painting',
    'paintings',
    'artwork',
    'artworks',
    'drawing',
    'drawings',
    'illustration',
    'illustrations',
    'engraving',
    'engravings',
    'sketch',
    'sketches',
    'google art project',
    'digital representation of 2d work',
    'museum collection',
    'still life',
    'watercolor',
    'watercolour',
    'oil painting',
    'oil on canvas',
    'oil on panel',
    'lithograph',
    'woodcut',
    'etching',
    'fresco',
    'tapestry',
    'mural',
    'pd-art',
    'clip art',
    'stamp',
    'stamps',
    'art museum',
    'art gallery',
    'national gallery',
    'museum of art',
)


def _is_art_category(category_title: str) -> bool:
    lowered = category_title.lower()
    return any(keyword in lowered for keyword in _ART_EXCLUSION_KEYWORDS)


# A second, real problem found while re-verifying the Gierymski fix live:
# excluding the painting from "Grey" Orange's real candidate list didn't
# make a real orange photo win — the next-ranked candidate was a real,
# genuinely-licensed PHOTOGRAPH of a completely unrelated animal
# (`File:Front_view_of_a_resting_Canis_lupus_ssp.jpg` — a grey wolf), which
# the art-exclusion gate above correctly leaves alone since it isn't art at
# all. The root cause: "Grey" (a variety-name descriptor word) and "Orange"
# (which is both the fruit AND a common place-name/color word — "Orange
# River", "Orange Free State", "Orange Julep") are individually common
# enough that Commons' relevance ranking surfaces unrelated real photos
# ahead of the actual fruit. Same generic-vs-distinctive-token idea this
# codebase already uses for exactly this kind of problem
# (openfoodfacts_client.py's `_GENERIC_COMMODITY_WORDS` /
# `_distinctive_terms`, Part 8.3 of VARIETY_GALLERY_METHODOLOGY.md) —
# reused here rather than invented fresh. A candidate is only accepted if
# its own title+categories text contains at least one term from
# `variety_name`/`species_label` that ISN'T one of these generic
# color/quality descriptor words a produce variety name commonly carries —
# "grey" alone can't anchor a match, but "orange"/"citrus"/"sinensis" can.
_GENERIC_DESCRIPTOR_WORDS = {
    'grey', 'gray', 'red', 'green', 'yellow', 'white', 'black', 'blue',
    'purple', 'golden', 'gold', 'brown', 'pink', 'giant', 'dwarf', 'wild',
    'sweet', 'sour', 'bitter', 'common', 'local', 'regional', 'small',
    'large', 'big', 'old', 'new', 'hybrid', 'heirloom', 'variety',
    'the', 'and', 'for', 'with',
}

_TOKEN_RE = re.compile(r'[a-zA-Z]+')


def _anchor_terms(variety_name: str, species_label: str) -> list[str]:
    tokens = [t for t in _TOKEN_RE.findall(f'{variety_name} {species_label}'.lower()) if len(t) > 2]
    distinctive = [t for t in tokens if t not in _GENERIC_DESCRIPTOR_WORDS]
    # If literally every token was a generic descriptor (unlikely, but
    # never silently block every candidate over it), fall back to using
    # all of them rather than anchoring on nothing.
    return distinctive or tokens


# A real false-positive found while verifying the anchor-term check itself
# live, one layer deeper than expected: the wolf photo above still passed
# because ITS OWN categories include `Category:Black, cream, gray, green,
# orange, red, white` — a real Commons convention that auto/manually tags a
# photo with its dominant on-screen COLORS, comma-separated. "orange" the
# color is a real substring match against "orange" the fruit's anchor term,
# purely coincidentally. Confirmed live via `_fetch_categories` on that
# exact file. Since "orange" the citrus fruit happens to share a name with
# a basic color word (unlike "tomato"/"bean"/"rice"/... ), a bare
# color-palette category can't be told apart from a real subject-matter
# category by keyword alone — so a category that IS one (every
# comma-separated token in it is itself a basic color name) is stripped out
# of the anchor-matching haystack entirely before the check runs, rather
# than trusted as a real subject signal.
_COLOR_PALETTE_WORDS = {
    'black', 'white', 'gray', 'grey', 'red', 'orange', 'yellow', 'green',
    'blue', 'purple', 'pink', 'brown', 'cream', 'tan', 'gold', 'silver',
    'beige', 'maroon', 'navy', 'teal', 'magenta', 'cyan', 'violet', 'ivory',
}


def _is_color_palette_category(category_title: str) -> bool:
    body = category_title.split(':', 1)[-1]
    tokens = [t.strip().lower() for t in body.split(',') if t.strip()]
    return len(tokens) >= 2 and all(t in _COLOR_PALETTE_WORDS for t in tokens)


# A third and fourth real false-positive, found re-verifying yet again
# after the color-palette fix — first `Irrigation_Project_along_the_Orange
# _River.jpg` (a NASA satellite photo of an actual river named Orange),
# then, after trying a real but ultimately unbounded blacklist of
# disambiguating qualifier words (river/free state/colour/julep/...), a
# THIRD case slipped through anyway: `Category:Orange sky in North
# Rhine-Westphalia`, tagging a real landscape/sunrise photo purely because
# its sky happened to look orange-colored — an open-ended natural-language
# use of "orange" as a plain color adjective, not any specific place/model
# name a blacklist could ever fully enumerate. "orange" is a genuinely
# pathological anchor word for this app's own real "Grey" Orange case
# specifically (Commons uses it as a color adjective constantly, well
# beyond the strict comma-separated color-palette categories already
# handled above) — confirmed live across four distinct, real false-positive
# shapes chasing this one case. Rather than keep extending an open-ended
# negative (qualifier) list, this flips to a bounded POSITIVE requirement:
# for a known-ambiguous anchor word, the SAME fragment it appears in must
# also carry a real produce/fruit-context word before it counts as a match
# at all — a bare, unqualified Commons category like the real
# `Category:Oranges` (containing "oranges", itself in the list) still
# validates normally; "orange sky", "Orange River", "Orange Free State",
# etc. do not, without needing to name each one. `_AMBIGUOUS_ANCHOR_WORDS`
# is deliberately small and grows only from a real case like this one, not
# guessed preemptively.
_AMBIGUOUS_ANCHOR_WORDS = {'orange'}
_PRODUCE_CONTEXT_WORDS = (
    'fruit', 'fruits', 'citrus', 'tree', 'trees', 'orchard', 'orchards',
    'harvest', 'produce', 'crop', 'crops', 'plant', 'plants', 'cultivar',
    'cultivars', 'juice', 'peel', 'grove', 'oranges',
)


def _term_matches_fragment(term: str, fragment_lower: str) -> bool:
    if term not in fragment_lower:
        return False
    if term not in _AMBIGUOUS_ANCHOR_WORDS:
        return True
    return any(context_word in fragment_lower for context_word in _PRODUCE_CONTEXT_WORDS)


def _is_relevant_candidate(anchor_terms: list[str], title: str, categories: list[str]) -> bool:
    if not anchor_terms:
        return True
    subject_categories = [c for c in categories if not _is_color_palette_category(c)]
    fragments = [title.lower()] + [c.lower() for c in subject_categories]
    return any(_term_matches_fragment(term, fragment) for term in anchor_terms for fragment in fragments)


def _fetch_categories(title: str) -> list[str]:
    """Real Commons categories for one file, e.g. ['Category:Paintings by
    ...', ...] — used only as the art-exclusion hard gate below. Never
    raises; a failed/empty lookup is treated as "no categories", which lets
    the candidate through the category gate (the MIME/license checks
    upstream still apply) rather than silently rejecting every candidate
    just because this one extra lookup failed."""
    try:
        response = httpx.get(
            API_URL,
            params={'action': 'query', 'titles': title, 'prop': 'categories', 'cllimit': 50, 'format': 'json'},
            headers={'User-Agent': _USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        pages = ((data.get('query') or {}).get('pages')) or {}
        for page in pages.values():
            return [c.get('title', '') for c in (page.get('categories') or [])]
    except Exception:
        pass
    return []


def _search_and_filter(query: str, anchor_terms: list[str]) -> Optional[dict]:
    """One real search + candidate-filter pass for `query` — the shared
    body both stages of `find_variety_image` run. Returns the first
    candidate (in Commons' own relevance order) that is a real photo file,
    has usable license metadata, passes the art-exclusion category gate,
    AND is actually about this variety/species (`anchor_terms`, see
    `_anchor_terms`) — or None if nothing in this pass's results survives
    all four checks."""
    try:
        search_response = httpx.get(
            API_URL,
            params={
                'action': 'query',
                'list': 'search',
                'srnamespace': 6,
                # 10, not 5: confirmed live that Commons' own relevance
                # ordering for a query built from a genuinely ambiguous
                # variety/species name pairing (ties/near-ties
                # re-ordering slightly between otherwise-identical live
                # requests) can push a real, relevant photo just outside a
                # 5-result window on one call and back inside it on the
                # next — widening the pool costs one extra imageinfo/
                # categories lookup at most per extra candidate actually
                # inspected (the loop below still stops at the first
                # candidate that passes every gate), not five more calls
                # regardless.
                'srlimit': 10,
                'srsearch': f'{query} filetype:bitmap',
                'format': 'json',
            },
            headers={'User-Agent': _USER_AGENT},
            timeout=TIMEOUT,
        )
        search_response.raise_for_status()
        search_data = search_response.json()
        hits = ((search_data.get('query') or {}).get('search')) or []
        candidate_titles = [hit['title'] for hit in hits if hit['title'].lower().endswith(_ALLOWED_EXTENSIONS)]
        if not candidate_titles:
            return None

        info_response = httpx.get(
            API_URL,
            params={'action': 'query', 'titles': '|'.join(candidate_titles), 'prop': 'imageinfo', 'iiprop': 'url|extmetadata|mime', 'format': 'json'},
            headers={'User-Agent': _USER_AGENT},
            timeout=TIMEOUT,
        )
        info_response.raise_for_status()
        info_data = info_response.json()
        pages = ((info_data.get('query') or {}).get('pages')) or {}

        # Preserve the search's own relevance order — `pages` is keyed by
        # pageid, not title, and dict iteration order isn't guaranteed to
        # match candidate_titles.
        pages_by_title = {page.get('title'): page for page in pages.values()}
        for title in candidate_titles:
            page = pages_by_title.get(title)
            if not page or not page.get('imageinfo'):
                continue
            image_info = page['imageinfo'][0]
            if not (image_info.get('mime') or '').startswith('image/'):
                continue
            extmeta = image_info.get('extmetadata') or {}
            license_name = (extmeta.get('LicenseShortName') or {}).get('value')
            if not license_name:
                # No usable license metadata at all — try the next
                # candidate rather than showing an unattributable image.
                continue
            # Hard gate: reject a real Commons artwork/painting/illustration
            # reproduction before it's ever considered further, regardless
            # of how legitimate its license/MIME type look (see module
            # docstring — both looked identical to a real photo's for the
            # Gierymski painting already in this app's own database).
            categories = _fetch_categories(title)
            if any(_is_art_category(category) for category in categories):
                continue
            # Second gate (see `_anchor_terms`'s own docstring for the real
            # case this caught): a real, non-art photo that just happens to
            # rank highly on a shared generic descriptor word is still the
            # wrong image — reject it and keep looking rather than accept
            # the first non-art hit unconditionally.
            if not _is_relevant_candidate(anchor_terms, title, categories):
                continue
            attribution = _strip_html((extmeta.get('Artist') or {}).get('value')) or _strip_html((extmeta.get('Attribution') or {}).get('value'))
            return {
                'url': image_info.get('url'),
                'license': license_name,
                'attribution': attribution or 'Wikimedia Commons contributor (see source page)',
                'source_url': image_info.get('descriptionurl'),
            }
        return None
    except Exception:
        return None


def find_variety_image(variety_name: str, species_label: str) -> Optional[dict]:
    """Searches Commons' File namespace for a real photo of `variety_name`
    (a species-context-biased query first, then a narrower fallback query —
    see module docstring for why both stages exist and what each actually
    contributes empirically), restricted to real photo files with usable
    license metadata AND passing the art-exclusion category gate. Returns
    {'url', 'license', 'attribution', 'source_url'} or None if Commons has
    no usable, real-photo result or the call fails for any reason — callers
    never substitute anything else in its place."""
    anchor_terms = _anchor_terms(variety_name, species_label)
    biased_query = f'{variety_name} {species_label} fruit photograph'
    result = _search_and_filter(biased_query, anchor_terms)
    if result is not None:
        return result
    fallback_query = f'{variety_name} {species_label}'
    return _search_and_filter(fallback_query, anchor_terms)
