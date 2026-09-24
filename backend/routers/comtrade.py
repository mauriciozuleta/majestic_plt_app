"""Global Trade Data module — UN Comtrade import/export figures by country
and HS product category. Global, not per-company: it has its own top-level
sidebar entry (see src/components/globalTradeData/GlobalTradeDataView.jsx),
not a tab nested under any one company's Operations view, the same way
Market Analysis, Simulations and the rest of the top-level sidebar items
aren't scoped to a company either.

Security: the UN Comtrade subscription key is attached to the outgoing
request only here, server-side (comtrade/client.py), read from the
COMTRADE_API_KEY environment variable — it's never sent to, stored in, or
readable from the browser. Every call the frontend makes goes through these
three endpoints instead of ever talking to Comtrade directly.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..comtrade import client
from ..comtrade.classification import list_searchable_hs_codes
from ..comtrade.countries import list_tracked_countries
from ..database import get_db
from ..trade_sources import discovery
from ..trade_sources.fetch import fetch_categories, fetch_products, fetch_subheadings

router = APIRouter()

FLOWS = {'M', 'X'}
# The most recent year worth TRYING first — not a guarantee it has data.
# Comtrade typically takes a year or more to finalize a country's figures,
# so a country that hasn't reported yet for this year is expected, not an
# error: the frontend probes this year first and walks backward itself
# (see resolveLatestYear in GlobalTradeDataView.jsx) until it finds one
# that actually has data, since that varies country by country and even
# flow by flow.
DEFAULT_YEAR_LAG = 1


def _flow(value: str) -> str:
    flow = value.upper().strip()
    if flow not in FLOWS:
        raise HTTPException(status_code=400, detail='flow must be M (imports) or X (exports).')
    return flow


@router.get('/api/trade/countries')
def list_trade_countries(db: Session = Depends(get_db)):
    """Every country Comtrade currently has a reporterCode for (see
    comtrade/countries.py), each tagged with the same geographic `region`
    Commercial Structure uses — joined by ISO alpha-2 against
    CountryReferenceCatalog, the same reference table
    /reference-regions and /reference-countries read from — so the Global
    Trade Data page can group its own country dropdown by region the same
    way. `region` is None for a Comtrade country with no matching catalog
    row (a handful of small/unrecognized territories); the frontend just
    won't be able to place those under a region filter. Plus a sensible
    default year, so the frontend doesn't need its own copy of the
    "Comtrade lags behind the calendar" reasoning.

    Also carries each country's discovered `trade_data_source`/
    `trade_data_coverage`/`trade_data_coverage_note` (see
    trade_sources/discovery.py — None/None/None for a country discovery
    has never run for, which behaves exactly like 'comtrade') and
    `discovering` (a fallback chain is currently running for it in the
    background) — set here so a future TAM/downstream feature already has
    what it needs to carry a partial-coverage flag forward, and so this
    page's own bilateral-coverage badge has something to render."""
    countries = list_tracked_countries()
    catalog_by_iso2 = {
        row.country_code: row
        for row in db.query(
            models.CountryReferenceCatalog.country_code,
            models.CountryReferenceCatalog.region,
            models.CountryReferenceCatalog.trade_data_source,
            models.CountryReferenceCatalog.trade_data_coverage,
            models.CountryReferenceCatalog.trade_data_coverage_note,
            models.CountryReferenceCatalog.trade_data_source_checked_at,
        )
        if row.country_code
    }
    tagged = []
    for country in countries:
        catalog_row = catalog_by_iso2.get(country['iso2'])
        tagged.append(
            {
                **country,
                'region': catalog_row.region if catalog_row else None,
                'trade_data_source': catalog_row.trade_data_source if catalog_row else None,
                'trade_data_coverage': catalog_row.trade_data_coverage if catalog_row else None,
                'trade_data_coverage_note': catalog_row.trade_data_coverage_note if catalog_row else None,
                'trade_data_source_checked_at': catalog_row.trade_data_source_checked_at if catalog_row else None,
                'discovering': discovery.is_discovering(country['iso2']) if country.get('iso2') else False,
            }
        )
    return {'countries': tagged, 'default_year': datetime.now(timezone.utc).year - DEFAULT_YEAR_LAG}


def _catalog_row_for_reporter(db: Session, reporter_code: int) -> models.CountryReferenceCatalog | None:
    """The CountryReferenceCatalog row for a Comtrade reporterCode, via the
    same reporter_code -> iso2 -> country_code join used everywhere else
    (see list_trade_countries above, and comtrade/countries.py's own
    reasoning for why iso2 is the only safe bridge between the two code
    spaces). None for a reporter with no iso2, or no matching catalog row
    — treated identically to an undiscovered country downstream."""
    for row in list_tracked_countries():
        if row.get('reporter_code') == reporter_code:
            if not row.get('iso2'):
                return None
            return db.query(models.CountryReferenceCatalog).filter_by(country_code=row['iso2']).first()
    return None


def _source_envelope(catalog_row: models.CountryReferenceCatalog | None) -> dict:
    return {
        'trade_data_source': (catalog_row.trade_data_source if catalog_row else None) or 'comtrade',
        'trade_data_coverage': (catalog_row.trade_data_coverage if catalog_row else None) or 'total',
        'trade_data_coverage_note': catalog_row.trade_data_coverage_note if catalog_row else None,
    }


@router.get('/api/trade/hs-products')
def list_hs_products():
    """Every 4-digit (heading) and 6-digit (subheading) HS code Comtrade
    knows about, as [{hs_code, level, chapter, heading, description}] — the
    catalog the frontend's product search box matches against. `level`
    tells the frontend which drill-down view a match opens (4 -> the
    product view, 6 -> the subheading view). Fetched once by the frontend
    and cached there for the session (see globalTradeData.js), not
    re-requested per keystroke; this endpoint itself never touches
    Comtrade's authenticated, quota-limited data API, only the free
    reference file already cached on disk (comtrade/classification.py), so
    calling it costs nothing against the 500-calls/day limit."""
    return {'products': list_searchable_hs_codes()}


@router.get('/api/trade/categories')
def trade_categories(
    country: int = Query(..., description='Comtrade reporterCode, from /api/trade/countries'),
    year: int = Query(...),
    flow: str = Query('M', description='M = imports, X = exports'),
    db: Session = Depends(get_db),
):
    flow = _flow(flow)
    catalog_row = _catalog_row_for_reporter(db, country)
    try:
        rows = fetch_categories(db, catalog_row, country, year, flow)
    except client.ComtradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    # has_data lets the frontend show an explicit "nothing reported" state
    # instead of an empty table or treating a real, valid empty result (a
    # small territory with nothing filed for that year) as an error.
    return {
        'country': country,
        'year': year,
        'flow': flow,
        'has_data': len(rows) > 0,
        'rows': rows,
        **_source_envelope(catalog_row),
    }


@router.get('/api/trade/products')
def trade_products(
    country: int = Query(..., description='Comtrade reporterCode, from /api/trade/countries'),
    year: int = Query(...),
    chapter: str = Query(..., description='HS 2-digit chapter to drill into, from /api/trade/categories'),
    flow: str = Query('M', description='M = imports, X = exports'),
    db: Session = Depends(get_db),
):
    flow = _flow(flow)
    catalog_row = _catalog_row_for_reporter(db, country)
    try:
        rows = fetch_products(db, catalog_row, country, year, flow, chapter)
    except client.ComtradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        'country': country,
        'year': year,
        'chapter': chapter,
        'flow': flow,
        'has_data': len(rows) > 0,
        'rows': rows,
        **_source_envelope(catalog_row),
    }


@router.get('/api/trade/subheadings')
def trade_subheadings(
    country: int = Query(..., description='Comtrade reporterCode, from /api/trade/countries'),
    year: int = Query(...),
    heading: str = Query(..., description='HS 4-digit heading to drill into, from /api/trade/products'),
    flow: str = Query('M', description='M = imports, X = exports'),
    db: Session = Depends(get_db),
):
    """The final drill-down level: 6-digit subheadings within one 4-digit
    heading — the deepest internationally standardized HS level."""
    flow = _flow(flow)
    catalog_row = _catalog_row_for_reporter(db, country)
    try:
        rows = fetch_subheadings(db, catalog_row, country, year, flow, heading)
    except client.ComtradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        'country': country,
        'year': year,
        'heading': heading,
        'flow': flow,
        'has_data': len(rows) > 0,
        'rows': rows,
        **_source_envelope(catalog_row),
    }


@router.get('/api/trade/countries/{country_code}/source-status')
def trade_source_status(country_code: str, db: Session = Depends(get_db)):
    """Lightweight polling target for the recheck control (see
    createCommercialCountry's discovery trigger and
    POST .../recheck-source below) — the frontend polls this instead of
    re-fetching the whole /api/trade/countries list while a fallback chain
    is running in the background."""
    country_code = country_code.upper()
    row = db.query(models.CountryReferenceCatalog).filter_by(country_code=country_code).first()
    if not row:
        raise HTTPException(status_code=404, detail='Country not found in the reference catalog.')
    return {
        'country_code': country_code,
        'trade_data_source': row.trade_data_source,
        'trade_data_coverage': row.trade_data_coverage,
        'trade_data_coverage_note': row.trade_data_coverage_note,
        'trade_data_source_checked_at': row.trade_data_source_checked_at,
        'discovering': discovery.is_discovering(country_code),
        'error': discovery.discovery_error(country_code),
    }


@router.post('/api/trade/countries/{country_code}/recheck-source')
def recheck_trade_source(country_code: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Unconditionally re-runs the full discovery chain (Comtrade check,
    then the fallback chain if that's empty) for one country, overwriting
    its stored fields — for when Comtrade later starts covering a country
    that had none, or a better fallback source is found. Unlike
    create_country's own trigger, this never skips just because a source
    is already stored."""
    country_code = country_code.upper()
    row = db.query(models.CountryReferenceCatalog).filter_by(country_code=country_code).first()
    if not row:
        raise HTTPException(status_code=404, detail='Country not found in the reference catalog.')
    return discovery.trigger(background_tasks, db, country_code, row.name)
