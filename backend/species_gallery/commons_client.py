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


def find_variety_image(query: str) -> Optional[dict]:
    """Searches Commons' File namespace for `query`, restricted to real
    photo files, and fetches the first genuine-photo result's real
    imageinfo (direct image URL + extmetadata license fields). Returns
    {'url', 'license', 'attribution', 'source_url'} or None if Commons has
    no usable result or the call fails for any reason — callers never
    substitute anything else in its place."""
    try:
        search_response = httpx.get(
            API_URL,
            params={
                'action': 'query',
                'list': 'search',
                'srnamespace': 6,
                'srlimit': 5,
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
