"""Small cached JSON GET with retry and exponential backoff, shared by the provider connectors.

Only the connectors call this, always with a base URL fixed in their own code — user input is never turned into a free-form URL.
Tests replace `get_json` (or `fetch`) with a fake, so no automated test reaches the network.
"""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).resolve().parent / 'cache'
RETRY_STATUS = {429, 500, 502, 503, 504}


class ProviderError(Exception):
    """A provider call failed after the retries (network error, bad status, malformed answer)."""


def _cache_path(url: str, params: dict | None) -> Path:
    key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:40]
    return CACHE_DIR / f'{key}.json'


def fetch(url: str, params: dict | None, headers: dict | None, timeout: float) -> httpx.Response:
    return httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)


def get_json(url: str, params: dict | None = None, *, headers: dict | None = None, ttl_hours: float = 24, retries: int = 3, backoff: float = 0.5, timeout: float = 30.0):
    """GET `url` and return the parsed JSON. Answers are cached on disk for `ttl_hours` (0 disables the cache); network errors, 429 and 5xx are
    retried with exponential backoff (0.5 s, 1 s, 2 s …)."""
    cache_file = _cache_path(url, params)
    if ttl_hours > 0 and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding='utf-8'))
            if datetime.fromisoformat(cached['at']) > datetime.now(timezone.utc) - timedelta(hours=ttl_hours):
                return cached['data']
        except (OSError, ValueError, KeyError):
            pass
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = fetch(url, params, headers, timeout)
            if response.status_code in RETRY_STATUS:
                last_error = ProviderError(f'{url} answered {response.status_code}')
            elif response.status_code >= 400:
                raise ProviderError(f'{url} answered {response.status_code}')
            else:
                data = response.json()
                if ttl_hours > 0:
                    try:
                        CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'data': data}), encoding='utf-8')
                    except OSError:
                        pass
                return data
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    raise ProviderError(f'{url} failed after {retries} attempts: {last_error}')
