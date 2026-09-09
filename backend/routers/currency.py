"""
Generic currency-conversion endpoint — not tied to any one feature. Any
screen that needs a live FX rate calls this the same way (see
ColombiaProductAnalysisView's COP->USD conversion for the first consumer).
"""

from fastapi import APIRouter, HTTPException, Query

from ..currency.exchange_rate import get_exchange_rate

router = APIRouter()


@router.get('/api/exchange-rate/')
def exchange_rate_api(
    from_currency: str = Query(alias='from'),
    to_currency: str = Query(default='USD', alias='to'),
):
    if not from_currency:
        raise HTTPException(status_code=400, detail='Missing from currency')
    try:
        rate = get_exchange_rate(from_currency, to_currency)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'rate': rate, 'from': from_currency.upper(), 'to': to_currency.upper()}
