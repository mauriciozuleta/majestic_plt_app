"""
Standalone currency-conversion utility, independent of FastAPI/any web
framework, so it can be unit-tested or reused from a CLI or other services.
Wraps ExchangeRate-API's "pair" endpoint (https://www.exchangerate-api.com/),
which returns a single conversion_rate for one currency pair — simpler than
fetching the full rate table for `from` and picking `to` out of it.

The API key is read server-side only from EXCHANGERATE_API_KEY — never
accept it from the frontend.
"""

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# FX rates don't need per-request freshness for wholesale-price decisions —
# this also protects the free tier's rate limit from repeated page loads.
_CACHE_TTL_SECONDS = 4 * 60 * 60
_rate_cache = {}


def get_exchange_rate(from_currency: str, to_currency: str, api_key: Optional[str] = None) -> float:
    """
    Get the exchange rate between two currencies.
    Returns the rate as a float (1 unit of from_currency = rate units of to_currency).
    Raises ConnectionError if the rate cannot be obtained.
    """
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    if from_currency == to_currency:
        return 1.0

    cache_key = (from_currency, to_currency)
    cached = _rate_cache.get(cache_key)
    if cached is not None and (time.monotonic() - cached[1]) < _CACHE_TTL_SECONDS:
        return cached[0]

    try:
        rate = _get_rate_from_exchangerate_api(from_currency, to_currency, api_key)
    except Exception as e:
        raise ConnectionError(f'Failed to get exchange rate from ExchangeRate-API: {e}') from e

    if rate is None:
        raise ConnectionError(f'ExchangeRate-API did not return a rate for {from_currency} to {to_currency}.')

    _rate_cache[cache_key] = (rate, time.monotonic())
    return rate


def _get_rate_from_exchangerate_api(from_currency: str, to_currency: str, api_key: Optional[str] = None) -> Optional[float]:
    if api_key is None:
        api_key = os.environ.get('EXCHANGERATE_API_KEY')
    if not api_key:
        logger.warning('No API key for ExchangeRate-API')
        return None

    url = f'https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_currency}/{to_currency}'
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('result') == 'success':
            return data.get('conversion_rate')
        logger.warning(f"ExchangeRate-API error: {data.get('error', 'Unknown error')}")
        return None
    except httpx.HTTPError as e:
        logger.warning(f'ExchangeRate-API request failed: {e}')
        return None


def convert_amount(amount: float, from_currency: str, to_currency: str, api_key: Optional[str] = None) -> float:
    """Convenience wrapper: convert a single amount using the live rate."""
    return amount * get_exchange_rate(from_currency, to_currency, api_key)
