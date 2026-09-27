"""Free, keyless FX for Market Opportunities (see routers/market_opportunities.py
and MARKET_SIZING_METHODOLOGY.md's Part 4) — deliberately separate from
currency/exchange_rate.py, which wraps a different, paid service
(ExchangeRate-API, key-gated) with only a 4-hour in-memory cache and no rate
date. Neither of those fits here: this feature needs a free/no-key path and
must store the rate's own date alongside every comparison record for
auditability. Left untouched per the spec — this module and that one never
call each other.

Every currency this app's own tracked countries actually use converts
independently to USD (never source-currency directly to target-currency
pairwise) — with N currencies, a common USD basis needs only N rates total,
not one per pair, and adding a new country later needs just one new rate.
This superseded an earlier version of this module (currency/frankfurter.py)
that wrapped Frankfurter/ECB — confirmed live that Frankfurter only covers
its own ~30 ECB-tracked currencies and does NOT include COP, JMD, XCD or
TTD, i.e. every real currency this app's tracked countries (Colombia,
Jamaica, Saint Lucia, Trinidad and Tobago) actually use, making every real
comparison permanently stuck at 'review' confidence. Replaced with
open.er-api.com (https://open.er-api.com/v6/latest/USD — confirmed live,
free, no key required), whose single bulk call covers all four: JMD
~158/USD, COP ~3264/USD, XCD exactly 2.70/USD (the long-standing fixed peg,
independently confirmed below), TTD ~6.80/USD (all directionally sane
against known real-world rates, checked before trusting this at scale).

DIRECTION, confirmed live and worth restating since getting it backwards
produces a plausible-looking but wrong number: the API returns, for each
currency, how many units of it equal 1 USD (e.g. `rates['JMD'] == 158.03`
means 1 USD = 158.03 JMD). Converting a LOCAL price to USD is therefore
`usd_value = local_value / rate` — a DIVISION, not a multiplication. This is
the exact same convention UsdExchangeRateCache (models.py) stores the rate
in, specifically so it stays checkable against a real-world quote by eye.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from .. import models

OPEN_ER_API_URL = 'https://open.er-api.com/v6/latest/USD'

# The Eastern Caribbean Central Bank has held XCD at exactly 2.70 per USD
# since 1976 — a currency-board peg, not a floating market rate, so there is
# nothing to look up or cache; independently confirmed against
# open.er-api.com's own live value for XCD (also exactly 2.70) before
# hardcoding this.
XCD_PEG_PER_USD = 2.70


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fetch_all_rates() -> Optional[dict]:
    try:
        response = httpx.get(OPEN_ER_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        return None
    if data.get('result') != 'success':
        return None
    rates = data.get('rates')
    if not isinstance(rates, dict):
        return None
    return rates


def get_usd_rate(db: Session, currency: str) -> Optional[dict]:
    """{'rate': float, 'date': 'YYYY-MM-DD'} — `rate` is how many units of
    `currency` equal 1 USD (divide a local price by this to get USD; see
    module docstring). None only if `currency` isn't a real 3-letter code,
    or open.er-api.com has no rate for it and nothing is cached either —
    never an invented number.

    USD and XCD short-circuit before any network call: USD-to-USD is
    trivially 1.0, and XCD is a fixed peg (see XCD_PEG_PER_USD above), so
    depending on a live rate for either would be strictly worse (a
    real-world identity/peg is more reliable than any API's daily fetch).
    Every other currency is served from today's cached row if one exists;
    otherwise ALL ~166 of open.er-api.com's currencies are fetched in one
    call and cached in bulk, so the very next currency looked up today
    (almost certainly needed in the same comparison run) is already a cache
    hit."""
    currency = (currency or '').upper().strip()
    if not currency or len(currency) != 3:
        return None
    if currency == 'USD':
        return {'rate': 1.0, 'date': _today()}
    if currency == 'XCD':
        return {'rate': XCD_PEG_PER_USD, 'date': _today()}

    today = _today()
    cached = (
        db.query(models.UsdExchangeRateCache)
        .filter_by(currency=currency)
        .order_by(models.UsdExchangeRateCache.fetched_at.desc())
        .first()
    )
    if cached and cached.fetched_at[:10] == today:
        return {'rate': cached.rate, 'date': cached.rate_date}

    rates = _fetch_all_rates()
    if rates is None:
        # A real network/API failure — fall back to whatever's already
        # cached (a real, previously-fetched rate, just not from today)
        # rather than leaving the caller with nothing.
        return {'rate': cached.rate, 'date': cached.rate_date} if cached else None

    rate_date = today
    fetched_at = datetime.now(timezone.utc).isoformat()
    for code, rate in rates.items():
        code = str(code).upper().strip()
        if len(code) != 3 or not isinstance(rate, (int, float)):
            continue
        db.add(
            models.UsdExchangeRateCache(
                id=str(uuid.uuid4()),
                currency=code,
                rate_date=rate_date,
                rate=float(rate),
                fetched_at=fetched_at,
            )
        )
    db.commit()

    rate = rates.get(currency)
    if rate is None:
        return {'rate': cached.rate, 'date': cached.rate_date} if cached else None
    return {'rate': float(rate), 'date': rate_date}
