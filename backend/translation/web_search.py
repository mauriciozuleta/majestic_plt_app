"""Tier 4 of the Colombia product-name translation fallback chain (see
resolve.py) — reached only when Tier 3's local model isn't available or
returned nothing usable. Deliberately NOT another Claude/LLM call (the
whole point of this chain is to stop spending API calls translating
product names) — a plain web search via Google's Custom Search JSON API,
with a heuristic extraction of an English candidate from the result
snippets, not a full page fetch/scrape.

Needs a Search Engine ID configured to search the open web (not just a
specific site) and an API key — both free to create at
https://programmablesearchengine.google.com/ and
https://developers.google.com/custom-search/v1/introduction (100 queries/
day on the free tier), read from GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX.
Returns None when either is unset, same as any other optional integration
in this app — Tier 4 then simply has nothing to offer, same as if the
search itself found nothing.

The least reliable tier by design: a snippet-scraped guess, never a
verified translation. Always tagged as such by resolve.py, and additionally
flagged as lower-confidence than Tier 3.
"""

import os
import re

import httpx

SEARCH_URL = 'https://www.googleapis.com/customsearch/v1'
QUERY_SUFFIX = 'traducción inglés fruta verdura'
RESULTS_PER_QUERY = 5

# A short English phrase immediately paired with the Spanish term in a
# snippet ("cidra is a chayote", "chayote (cidra)", "cidra (chayote)") is
# the closest a snippet-only heuristic can get to "the English name"
# without fetching and parsing the whole page.
_PAIR_TEMPLATES = [
    r'\b{term}\b\s+(?:is|means|=|-|:)\s+(?:an?\s+)?([A-Za-z][A-Za-z \-]{{2,30}})',
    r'([A-Za-z][A-Za-z \-]{{2,30}})\s*\(\s*{term}\s*\)',
    r'{term}\s*\(\s*([A-Za-z][A-Za-z \-]{{2,30}})\s*\)',
]


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get('GOOGLE_SEARCH_API_KEY')
    cx = os.environ.get('GOOGLE_SEARCH_CX')
    return (api_key, cx) if api_key and cx else None


def _extract_candidate(term: str, text: str) -> str | None:
    escaped = re.escape(term)
    for template in _PAIR_TEMPLATES:
        match = re.search(template.format(term=escaped), text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(' .,-')
            if candidate and candidate.lower() != term.lower():
                return candidate
    return None


def search_translation(name_es: str) -> str | None:
    """Best-effort English name for a Spanish product name, scraped from
    search-result snippets, or None if no credentials are configured, the
    request fails, or no snippet yields a plausible candidate."""
    creds = _credentials()
    if not creds or not (name_es or '').strip():
        return None
    api_key, cx = creds
    query = f'{name_es} {QUERY_SUFFIX}'
    try:
        response = httpx.get(
            SEARCH_URL, params={'key': api_key, 'cx': cx, 'q': query, 'num': RESULTS_PER_QUERY}, timeout=15
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    for item in response.json().get('items', []):
        snippet = f"{item.get('title', '')} {item.get('snippet', '')}"
        candidate = _extract_candidate(name_es, snippet)
        if candidate:
            return candidate.title()
    return None
