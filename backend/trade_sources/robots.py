"""Shared robots.txt permission check — used before treating any newly
discovered tier 1/2 source (registry.py) as usable, per the fallback
chain's own rule (discovery.py): "before using any newly discovered
source, check its robots.txt / terms of access; if blocked, treat as
failed for that tier."

Not used for tier 3 (fred_client.py): FRED is a key-authenticated REST API
with its own published terms (https://fred.stlouisfed.org/docs/api/), not
a scraped website — robots.txt has no meaning for an API endpoint reached
directly with an API key, the same way COMTRADE_API_KEY-authenticated
calls in comtrade/client.py never consult UN Comtrade's robots.txt either.
"""

import urllib.robotparser
from urllib.parse import urlparse

USER_AGENT = 'MajesticTradeDataBot/1.0'


def is_allowed(url: str, user_agent: str = USER_AGENT) -> tuple[bool, str]:
    """(allowed, reason) for fetching `url` as `user_agent`. A robots.txt
    that can't be fetched at all (no file, network error, non-200) is
    treated as "allowed" — the standard, widely-followed convention for a
    site that hasn't declared any crawl restrictions — never as a reason
    to block a real, otherwise-accessible source."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False, f'not a fetchable URL: {url!r}'

    robots_url = f'{parsed.scheme}://{parsed.netloc}/robots.txt'
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception as error:
        return True, f'robots.txt unreachable ({error}) — treated as allowed'

    try:
        allowed = parser.can_fetch(user_agent, url)
    except Exception as error:
        return True, f'robots.txt unparseable ({error}) — treated as allowed'
    return allowed, ('allowed by robots.txt' if allowed else f'disallowed by robots.txt ({robots_url})')
