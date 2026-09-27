"""LangSearch web search — the bootstrap step's only source of free-text
characteristics research (spec section 3.1). Real, free-tier, but NOT
keyless: confirmed via LangSearch's own published API docs (POST
https://api.langsearch.com/v1/web-search, Authorization: Bearer
<LANGSEARCH_API_KEY>, JSON body {query, count, contents:{text:true}}) — a
real account + key from https://langsearch.com is required, same as this
app's other optional-but-free-tier keyed services (COMTRADE_API_KEY,
FRED_API_KEY). Wired the same way: read server-side only from the
LANGSEARCH_API_KEY env var, and when it's unset this reports
`configured: False` and does nothing else — never blocks the rest of a
bootstrap (Tier B/Wikimedia sourcing has no dependency on this succeeding).

No key is configured in this development environment as of this writing —
`is_configured()` genuinely returns False here, and every bootstrap that
reaches this step reports 'langsearch not configured' rather than
fabricating a search result.
"""

import os
from typing import Optional

import httpx

SEARCH_URL = 'https://api.langsearch.com/v1/web-search'
TIMEOUT = 20


def is_configured() -> bool:
    return bool(os.environ.get('LANGSEARCH_API_KEY'))


def web_search(query: str, count: int = 5) -> Optional[dict]:
    """Returns {'results': [{'name','url','snippet','text'}, ...]} on
    success, or None if LANGSEARCH_API_KEY isn't set or the call fails —
    callers (bootstrap.py) treat None exactly like "no web-search signal
    available" and continue with whatever else they have (never blocking
    the rest of a bootstrap on this one sub-step)."""
    api_key = os.environ.get('LANGSEARCH_API_KEY')
    if not api_key:
        return None
    try:
        response = httpx.post(
            SEARCH_URL,
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
            json={'query': query, 'count': count, 'contents': {'text': True}},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    data = payload.get('data') or {}
    web_pages = (data.get('webPages') or {}).get('value') or []
    results = [
        {
            'name': item.get('name'),
            'url': item.get('url'),
            'snippet': item.get('snippet'),
            'text': item.get('text'),
        }
        for item in web_pages
    ]
    return {'results': results}
