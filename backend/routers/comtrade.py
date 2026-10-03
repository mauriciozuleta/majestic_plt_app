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

from .. import market_size_store, models
from ..comtrade import client
from ..comtrade.classification import list_searchable_hs_codes
from ..comtrade.countries import list_tracked_countries
from ..database import get_db
from ..estimation import regression
from ..trade_sources import discovery, worldbank
from ..trade_sources.fetch import fetch_all_subheadings, fetch_categories, fetch_products, fetch_subheadings
from .commercial_structure import get_market_analysis_regions

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
# Same probe depth GlobalTradeDataView.jsx's YEAR_PROBE_ATTEMPTS uses on the
# frontend — ported here for /api/trade/sam-overview, which resolves each
# country's own "most recent year with data" itself (once per country, see
# that endpoint) rather than relying on a client-side probe loop.
YEAR_PROBE_ATTEMPTS = 6


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


def _resolve_year_and_rows(
    db: Session, catalog_row: models.CountryReferenceCatalog | None, reporter_code: int, flow: str, default_year: int
) -> tuple[int | None, list[dict]]:
    """One country's own "most recent year with reported data" — tried
    newest-first, walked backward exactly like GlobalTradeDataView.jsx's own
    year-probe effect, except resolved once here (not once per chapter):
    fetch_categories already returns every chapter's row in a single call,
    so probing a year IS fetching that year's full category set — there is
    nothing left to do per-chapter afterward but pick the rows out of
    whichever probe first came back non-empty. Returns (None, []) if no
    probed year had any data at all."""
    for offset in range(YEAR_PROBE_ATTEMPTS):
        candidate = default_year - offset
        try:
            rows = fetch_categories(db, catalog_row, reporter_code, candidate, flow)
        except client.ComtradeError:
            continue
        if rows:
            return candidate, rows
    return None, []


@router.get('/api/trade/sam-overview')
def sam_overview(
    chapters: str = Query(..., description='Comma-separated HS 2-digit chapters to include — the qualifying (green) categories, computed client-side by buildCategoryCoverage().'),
    flow: str = Query('M', description='M = imports, X = exports — SAM uses M.'),
    db: Session = Depends(get_db),
):
    """SAM Overview — now a PERSISTED aggregate, not a recompute-on-every-view
    endpoint: once computed at least once, this returns the stored result
    straight from the database (`MarketSizeSnapshot`, kind='sam') — no live
    Comtrade re-aggregation, no re-resolving qualifying chapters, nothing.
    The very first call (or after a chatbox/`refresh_sam_overview` recompute
    clears it) computes live via `_compute_sam_overview_data` below and
    persists the result in the same call, so the next view is instant. See
    MARKET_SIZING_METHODOLOGY.md for why chapters passed here are IGNORED
    once a stored snapshot exists (never used to silently auto-invalidate
    it) and `market_size_store.py` for the persistence itself.

    `_compute_sam_overview_data` does the real work: for every region in the
    portfolio (see get_market_analysis_regions), the real Comtrade 2-digit
    chapter import total for each qualifying category — summed only across
    countries in that region that actually reported that chapter for their
    own resolved year (a country with nothing for a chapter is excluded
    from that category's sum entirely, never treated as 0 — see
    fetch_categories' per-country year resolution below). A
    `bilateral`-coverage country's contribution is flagged both on its own
    breakdown line and on the category total it fed (true if ANY
    contributor was bilateral), so a mixed-source total never reads with
    the same confidence as an all-Comtrade one.

    A category only appears for a region if at least one of that region's
    countries actually contributed a value — an empty category is left out
    entirely rather than shown as a hollow zero (same exclusion rule as a
    single country's own missing chapter).

    A `us_census_fred`-sourced country's fetch_categories returns a single
    pseudo-row ('TOTAL') that never matches a real 2-digit chapter code, so
    it naturally never contributes here — that's the real limitation of
    that fallback tier, not a bug."""
    flow = _flow(flow)
    chapter_list = sorted({c.strip().zfill(2) for c in chapters.split(',') if c.strip()})
    if not chapter_list:
        raise HTTPException(status_code=400, detail='chapters must include at least one HS 2-digit chapter code.')

    stored = market_size_store.get_snapshot(db, 'sam')
    if stored:
        return stored['data']

    data = _compute_sam_overview_data(db, chapter_list, flow)
    return market_size_store.save_snapshot(db, 'sam', flow, chapter_list, data)


def _compute_sam_overview_data(db: Session, chapter_list: list[str], flow: str) -> dict:
    """The actual SAM Overview computation — see sam_overview's own
    docstring above for the full aggregation rules. Pulled out into its own
    function so it can be called both from the GET endpoint (first-ever
    compute) and from refresh_sam_overview (an unconditional recompute,
    triggered by the chatbox's 'refresh SAM' tool — see
    routers/assistant.py) without duplicating the logic."""
    default_year = datetime.now(timezone.utc).year - DEFAULT_YEAR_LAG
    reporter_by_iso2 = {row['iso2']: row['reporter_code'] for row in list_tracked_countries() if row.get('iso2')}

    regions = get_market_analysis_regions(db)
    result_regions = []
    for region in regions:
        # {chapter: {'value': float, 'bilateral': bool, 'countries': [...]}}
        totals = {chapter: {'value': 0.0, 'bilateral': False, 'countries': []} for chapter in chapter_list}
        for country in region['countries']:
            iso2 = (country['country_code'] or '').upper()
            reporter_code = reporter_by_iso2.get(iso2)
            if not reporter_code:
                continue
            catalog_row = db.query(models.CountryReferenceCatalog).filter_by(country_code=iso2).first()
            try:
                year, rows = _resolve_year_and_rows(db, catalog_row, reporter_code, flow, default_year)
            except client.ComtradeError:
                continue
            if not rows:
                continue
            is_bilateral = bool(catalog_row and catalog_row.trade_data_coverage == 'bilateral')
            rows_by_chapter = {row['hs_code']: row for row in rows if row.get('hs_code')}
            for chapter in chapter_list:
                row = rows_by_chapter.get(chapter)
                if not row:
                    continue
                bucket = totals[chapter]
                bucket['value'] += row['value']
                bucket['bilateral'] = bucket['bilateral'] or is_bilateral
                bucket['countries'].append(
                    {
                        'id': country['id'],
                        'name': country['name'],
                        'country_code': iso2,
                        'value': row['value'],
                        'bilateral': is_bilateral,
                        'year': year,
                    }
                )
        categories = [
            {
                'chapter': chapter,
                'value': bucket['value'],
                'bilateral': bucket['bilateral'],
                'countries': sorted(bucket['countries'], key=lambda item: item['value'], reverse=True),
            }
            for chapter, bucket in totals.items()
            if bucket['countries']
        ]
        result_regions.append({'region': region['region'], 'categories': categories})

    return {'flow': flow, 'default_year': default_year, 'regions': result_regions}


@router.get('/api/trade/product-sam')
def product_sam(
    region: str = Query(..., description='Market Analysis region name, as in /api/trade/sam-overview'),
    hs_codes: str = Query(..., description='Comma-separated 6-digit HS codes'),
    flow: str = Query('M', description='M = imports, X = exports — SAM uses M.'),
    db: Session = Depends(get_db),
):
    """Product-level SAM: each 6-digit HS code's import value for every
    active country of one region — per country, and summed for the region —
    rather than SAM Overview's whole 2-digit chapter. Each country uses its
    own most recent year with reported data (resolved exactly as SAM
    Overview does, from the cached chapter totals), and all of that
    country's 6-digit figures come from one cached Comtrade call
    (fetch_all_subheadings), so a region costs at most one call per country
    the first time and nothing after.

    A country that reported no imports of a code is left out of that code's
    figures (never counted as 0). `countries` lists every country of the
    region with its year and a status — 'ok', 'no_data' (nothing reported
    in any probed year), 'no_product_data' (no 6-digit breakdown, e.g. a
    fallback source with only a total), 'not_in_comtrade' or 'error' (with
    the reason, e.g. the daily call limit) — so a partial total says so."""
    flow = _flow(flow)
    codes = sorted({code.strip() for code in hs_codes.split(',') if code.strip().isdigit() and len(code.strip()) == 6})
    region_row = next((row for row in get_market_analysis_regions(db) if row['region'] == region), None)
    if not region_row:
        raise HTTPException(status_code=404, detail=f'Region not found: {region}')

    default_year = datetime.now(timezone.utc).year - DEFAULT_YEAR_LAG
    reporter_by_iso2 = {row['iso2']: row['reporter_code'] for row in list_tracked_countries() if row.get('iso2')}
    products = {code: {'region_total': 0.0, 'countries': {}} for code in codes}
    countries = []
    for country in region_row['countries']:
        entry = {'name': country['name'], 'year': None, 'status': 'ok'}
        countries.append(entry)
        iso2 = (country['country_code'] or '').upper()
        reporter_code = reporter_by_iso2.get(iso2)
        if not reporter_code:
            entry['status'] = 'not_in_comtrade'
            continue
        catalog_row = db.query(models.CountryReferenceCatalog).filter_by(country_code=iso2).first()
        year, _rows = _resolve_year_and_rows(db, catalog_row, reporter_code, flow, default_year)
        if year is None:
            entry['status'] = 'no_data'
            continue
        entry['year'] = year
        try:
            values = fetch_all_subheadings(db, catalog_row, reporter_code, year, flow)
        except client.ComtradeError as error:
            entry['status'] = 'error'
            entry['error'] = str(error)
            continue
        if not values:
            entry['status'] = 'no_product_data'
            continue
        for code in codes:
            value = values.get(code)
            if value is None:
                continue
            products[code]['countries'][country['name']] = {'value': value, 'year': year}
            products[code]['region_total'] += value

    for product in products.values():
        if not product['countries']:
            product['region_total'] = None
    return {'region': region, 'flow': flow, 'countries': countries, 'products': products}


def refresh_sam_overview(db: Session, chapters: str | None = None, flow: str = 'M') -> dict:
    """Unconditionally recomputes SAM Overview and overwrites the stored
    snapshot — called from the POST route below (a possible future UI
    refresh control) and directly, in-process, from the chatbox's
    'refresh_market_size' tool (routers/assistant.py), which has no browser
    to ask buildCategoryCoverage() for a fresh chapter list. `chapters` is
    therefore optional: pass it to recompute with an explicit scope, or omit
    it to reuse the qualifying-category scope of the last stored snapshot
    (the normal case — Comtrade's own published figures change over time
    even for the same categories, which is the actual reason to ask for a
    refresh). Raises if SAM has never been computed at all and no chapters
    were given, since there's no scope to recompute with."""
    flow = _flow(flow)
    chapter_list = sorted({c.strip().zfill(2) for c in chapters.split(',') if c.strip()}) if chapters else []
    if not chapter_list:
        stored = market_size_store.get_snapshot(db, 'sam')
        chapter_list = stored['chapters'] if stored and stored['chapters'] else []
    if not chapter_list:
        raise HTTPException(
            status_code=400,
            detail='SAM has never been computed yet — view the SAM Overview tab once first, or pass chapters explicitly.',
        )
    data = _compute_sam_overview_data(db, chapter_list, flow)
    return market_size_store.save_snapshot(db, 'sam', flow, chapter_list, data)


@router.post('/api/trade/sam-overview/refresh')
def refresh_sam_overview_endpoint(
    chapters: str | None = Query(None, description='Comma-separated HS 2-digit chapters — omit to reuse the last stored snapshot\'s own scope.'),
    flow: str = Query('M', description='M = imports, X = exports — SAM uses M.'),
    db: Session = Depends(get_db),
):
    return refresh_sam_overview(db, chapters, flow)


@router.get('/api/trade/sam-overview/summary')
def sam_overview_summary(db: Session = Depends(get_db)):
    """Lightweight figure for the Home page's SAM card: the stored
    snapshot's grand total (summed across every region/category) and how
    many distinct qualifying categories contributed to it — reads the
    persisted snapshot only, never computes or touches Comtrade, so Home
    never triggers any trade-data work. computed_at/total_value/
    category_count come back null/0/0 if SAM has never been computed yet
    (view Market Size ▸ SAM once to populate it)."""
    stored = market_size_store.get_snapshot(db, 'sam')
    if not stored:
        return {'computed_at': None, 'total_value': 0.0, 'category_count': 0}
    total_value = 0.0
    chapters_seen = set()
    for region in stored['data'].get('regions', []):
        for category in region.get('categories', []):
            total_value += category.get('value') or 0.0
            if category.get('chapter'):
                chapters_seen.add(category['chapter'])
    return {'computed_at': stored['computed_at'], 'total_value': total_value, 'category_count': len(chapters_seen)}


def _region_chapter_country_data(
    db: Session, region: dict, chapter_list: list[str], flow: str, default_year: int
) -> dict[str, dict]:
    """Per requested chapter, one region's own {'confirmed': [...],
    'gap': [...]} for SAM Overview's estimation layer (see
    sam_overview_estimates below):

    - `confirmed`: the STRICT training set — countries with a real,
      non-bilateral, true-Comtrade-sourced figure for that chapter only
      (deliberately narrower than sam_overview's own "has a SAM figure",
      which also counts bilateral coverage — see MARKET_SIZING_METHODOLOGY.md for why
      bilateral figures are excluded from training even though they're
      shown as real numbers elsewhere).
    - `gap`: every region country with NO existing row at all for that
      chapter — true-Comtrade or bilateral — whether or not Comtrade tracks
      that country at all. These are the only candidates estimation is ever
      allowed to fill; a country that already has ANY real figure (even a
      partial bilateral one) is never in `gap` and is therefore never
      estimated, matching "estimation only fills gaps, it must never
      override or second-guess a real number.\""""
    reporter_by_iso2 = {row['iso2']: row['reporter_code'] for row in list_tracked_countries() if row.get('iso2')}
    has_any_row: dict[str, set[str]] = {chapter: set() for chapter in chapter_list}
    per_chapter = {chapter: {'confirmed': [], 'gap': []} for chapter in chapter_list}

    for country in region['countries']:
        iso2 = (country['country_code'] or '').upper()
        if not iso2:
            continue
        reporter_code = reporter_by_iso2.get(iso2)
        catalog_row = db.query(models.CountryReferenceCatalog).filter_by(country_code=iso2).first()
        rows_by_chapter: dict[str, dict] = {}
        year = None
        if reporter_code:
            try:
                year, rows = _resolve_year_and_rows(db, catalog_row, reporter_code, flow, default_year)
            except client.ComtradeError:
                rows = []
            rows_by_chapter = {row['hs_code']: row for row in rows if row.get('hs_code')}

        source = (catalog_row.trade_data_source if catalog_row else None) or 'comtrade'
        coverage = (catalog_row.trade_data_coverage if catalog_row else None) or 'total'
        is_true_comtrade = source == 'comtrade' and coverage != 'bilateral'

        for chapter in chapter_list:
            row = rows_by_chapter.get(chapter)
            if not row:
                continue
            has_any_row[chapter].add(iso2)
            if is_true_comtrade:
                per_chapter[chapter]['confirmed'].append(
                    {'id': country['id'], 'name': country['name'], 'country_code': iso2, 'value': row['value'], 'year': year}
                )

    for country in region['countries']:
        iso2 = (country['country_code'] or '').upper()
        if not iso2:
            continue
        for chapter in chapter_list:
            if iso2 not in has_any_row[chapter]:
                per_chapter[chapter]['gap'].append({'id': country['id'], 'name': country['name'], 'country_code': iso2})

    return per_chapter


@router.get('/api/trade/sam-overview-estimates')
def sam_overview_estimates(
    chapters: str = Query(..., description='Same comma-separated qualifying (green) HS 2-digit chapters passed to /api/trade/sam-overview.'),
    flow: str = Query('M', description='M = imports, X = exports — SAM uses M.'),
    db: Session = Depends(get_db),
):
    """SAM Overview's opt-in estimation layer (see MARKET_SIZING_METHODOLOGY.md) — only
    ever called from the frontend when the "Include estimated values"
    toggle is switched ON (see SamPanel.jsx); the default Overview load
    never hits this endpoint or the World Bank API, so opting out costs
    nothing extra. For every qualifying chapter, in every region:

    1. Fits a population + GDP-per-capita regression (see
       backend/estimation/regression.py) against that region's own
       TRUE-Comtrade, non-bilateral countries for that chapter — the
       `confirmed` set from _region_chapter_country_data above.
    2. Below MIN_SAMPLE_SIZE confirmed countries, no model is fit at all —
       the category comes back with status 'insufficient_confirmed_data'
       and a ready-to-display explanation, never a silently missing row.
    3. Otherwise, applies the fitted model to every `gap` country (one with
       NO existing row at all for that chapter) using that country's own
       real population/GDP-per-capita from the World Bank — never to a
       country that already has a confirmed or bilateral figure, which
       keeps exactly what /api/trade/sam-overview already shows for it.

    Population/GDP-per-capita are fetched ONCE for every country across
    every region (they're category-independent facts) and reused for every
    chapter's model — see worldbank.fetch_population_and_gdp."""
    flow = _flow(flow)
    chapter_list = sorted({c.strip().zfill(2) for c in chapters.split(',') if c.strip()})
    if not chapter_list:
        raise HTTPException(status_code=400, detail='chapters must include at least one HS 2-digit chapter code.')

    default_year = datetime.now(timezone.utc).year - DEFAULT_YEAR_LAG
    regions = get_market_analysis_regions(db)

    all_iso2 = sorted(
        {(c['country_code'] or '').upper() for region in regions for c in region['countries'] if c.get('country_code')}
    )
    indicators = worldbank.fetch_population_and_gdp(db, all_iso2)

    result_regions = []
    for region in regions:
        per_chapter = _region_chapter_country_data(db, region, chapter_list, flow, default_year)
        categories = []
        for chapter in chapter_list:
            confirmed = per_chapter[chapter]['confirmed']
            gap = per_chapter[chapter]['gap']

            training_rows = []
            trained_countries = []
            for row in confirmed:
                indicator = indicators.get(row['country_code'], {})
                if indicator.get('population') is None or indicator.get('gdp_per_capita') is None:
                    # A confirmed-data country the World Bank itself has no
                    # population/GDP figure for can't be used as a training
                    # row (it has no predictors) — excluded from the model,
                    # not from sam_overview's own confirmed total.
                    continue
                training_rows.append(
                    {'population': indicator['population'], 'gdp_per_capita': indicator['gdp_per_capita'], 'value': row['value']}
                )
                trained_countries.append(row)

            sample_size = len(training_rows)
            if sample_size < regression.MIN_SAMPLE_SIZE:
                categories.append(
                    {
                        'chapter': chapter,
                        'status': 'insufficient_confirmed_data',
                        'message': f'Not enough confirmed data points to estimate this category ({sample_size} of {regression.MIN_SAMPLE_SIZE} minimum).',
                        'sample_size': sample_size,
                        'min_sample_size': regression.MIN_SAMPLE_SIZE,
                        'model': None,
                        'estimates': [],
                        'unavailable': [],
                    }
                )
                continue

            model = regression.fit_category_model(training_rows)
            estimates = []
            unavailable = []
            for country in gap:
                indicator = indicators.get(country['country_code'], {})
                if indicator.get('population') is None or indicator.get('gdp_per_capita') is None:
                    unavailable.append(
                        {**country, 'reason': 'No World Bank population/GDP-per-capita data available for this country.'}
                    )
                    continue
                predicted = regression.predict(model, indicator['population'], indicator['gdp_per_capita'])
                estimates.append(
                    {
                        'id': country['id'],
                        'name': country['name'],
                        'country_code': country['country_code'],
                        'predicted_value': predicted,
                        'low_confidence': model['low_confidence'],
                        'population': indicator['population'],
                        'population_year': indicator['population_year'],
                        'gdp_per_capita': indicator['gdp_per_capita'],
                        'gdp_per_capita_year': indicator['gdp_per_capita_year'],
                    }
                )

            categories.append(
                {
                    'chapter': chapter,
                    'status': 'estimated',
                    'message': None,
                    'sample_size': sample_size,
                    'min_sample_size': regression.MIN_SAMPLE_SIZE,
                    'model': {
                        'method': model['method'],
                        'r_squared': model['r_squared'],
                        'low_confidence': model['low_confidence'],
                        'sample_size': model['sample_size'],
                        'trained_countries': trained_countries,
                    },
                    'estimates': sorted(estimates, key=lambda item: item['predicted_value'], reverse=True),
                    'unavailable': unavailable,
                }
            )
        result_regions.append({'region': region['region'], 'categories': categories})

    return {
        'flow': flow,
        'default_year': default_year,
        'min_sample_size': regression.MIN_SAMPLE_SIZE,
        'low_confidence_r2_threshold': regression.LOW_CONFIDENCE_R2_THRESHOLD,
        'regions': result_regions,
    }


def _resolve_global_year_and_rows(db: Session, chapter: str, flow: str, default_year: int) -> tuple[int | None, list[dict]]:
    """One chapter's own "most recent year with any country reporting" —
    same newest-first probe as _resolve_year_and_rows above, just against
    the global (no-reporterCode) pull instead of one country's. Returns
    (None, []) if no probed year had any data at all (never happens in
    practice for a real HS chapter with any global trade, but guarded the
    same way every other probe in this module is)."""
    for offset in range(YEAR_PROBE_ATTEMPTS):
        candidate = default_year - offset
        try:
            rows = client.fetch_global_total(db, chapter, candidate, flow)
        except client.ComtradeError:
            continue
        if rows:
            return candidate, rows
    return None, []


@router.get('/api/trade/tam-global-overview')
def tam_global_overview(
    chapters: str = Query(..., description='Comma-separated HS 2-digit chapters to include — same qualifying (green) categories as /api/trade/sam-overview, computed client-side by buildCategoryCoverage().'),
    flow: str = Query('M', description='M = imports, X = exports — TAM uses M.'),
    db: Session = Depends(get_db),
):
    """TAM ▸ Overview — same PERSISTED-aggregate design as sam_overview
    above: once computed at least once, this returns the stored
    `MarketSizeSnapshot` (kind='tam') straight back, no live Comtrade
    re-aggregation. The first call (or after a recompute) computes via
    `_compute_tam_overview_data` and persists it in the same call. See
    MARKET_SIZING_METHODOLOGY.md — `chapters` passed here is IGNORED once a
    stored snapshot exists, same as SAM.

    `_compute_tam_overview_data` does the real work: real, unscoped global
    UN Comtrade import totals — one figure per qualifying chapter, summed
    across every country that reported it worldwide, not just this app's
    tracked Commercial Structure countries (that narrower, tracked-country
    figure is SAM, see sam_overview above). See MARKET_SIZING_METHODOLOGY.md
    Part 2 for the full mechanism; in short: reporterCode is omitted
    entirely (not set to 0 — Comtrade has no "World" reporter, confirmed
    empty live) so Comtrade returns one row per actual reporting country,
    resolved at each chapter's own most-recently-reported year (a global
    pull can lag a year or two behind "now" the same way a single country's
    can) and summed via client.fetch_global_total, which already applies
    this app's shared duplicate-row guard (motCode/partner2Code/customsCode
    all pinned to their "total" values — see client.py's _TOTALS_ONLY; this
    guard was extended with customsCode specifically while verifying this
    endpoint, after live testing found it silently double/triple-counted
    up to 37 of 166 real reporters for a single chapter/year otherwise).

    A chapter with no country reporting it in any probed year is left out
    entirely — never a hollow zero row, same exclusion rule as SAM's own."""
    flow = _flow(flow)
    chapter_list = sorted({c.strip().zfill(2) for c in chapters.split(',') if c.strip()})
    if not chapter_list:
        raise HTTPException(status_code=400, detail='chapters must include at least one HS 2-digit chapter code.')

    stored = market_size_store.get_snapshot(db, 'tam')
    if stored:
        return stored['data']

    data = _compute_tam_overview_data(db, chapter_list, flow)
    return market_size_store.save_snapshot(db, 'tam', flow, chapter_list, data)


def _compute_tam_overview_data(db: Session, chapter_list: list[str], flow: str) -> dict:
    """The actual TAM Overview computation — see tam_global_overview's own
    docstring above. Pulled out so it can be called both from the GET
    endpoint (first-ever compute) and refresh_tam_overview (an
    unconditional recompute triggered by the chatbox's 'refresh TAM' tool)."""
    default_year = datetime.now(timezone.utc).year - DEFAULT_YEAR_LAG
    reporter_names = {row['reporter_code']: row['name'] for row in list_tracked_countries()}

    categories = []
    for chapter in chapter_list:
        year, rows = _resolve_global_year_and_rows(db, chapter, flow, default_year)
        if not rows:
            continue
        countries = sorted(
            (
                {
                    'reporter_code': row['reporter_code'],
                    'name': reporter_names.get(row['reporter_code'], f"Reporter {row['reporter_code']}"),
                    'value': row['value'],
                }
                for row in rows
            ),
            key=lambda item: item['value'],
            reverse=True,
        )
        categories.append(
            {
                'chapter': chapter,
                'year': year,
                'value': sum(item['value'] for item in countries),
                'country_count': len(countries),
                'countries': countries,
            }
        )

    return {'flow': flow, 'default_year': default_year, 'categories': categories}


def refresh_tam_overview(db: Session, chapters: str | None = None, flow: str = 'M') -> dict:
    """TAM's own version of refresh_sam_overview above — same optional-
    chapters/reuse-last-scope behavior, same callers (a possible future UI
    refresh control, and the chatbox's 'refresh_market_size' tool)."""
    flow = _flow(flow)
    chapter_list = sorted({c.strip().zfill(2) for c in chapters.split(',') if c.strip()}) if chapters else []
    if not chapter_list:
        stored = market_size_store.get_snapshot(db, 'tam')
        chapter_list = stored['chapters'] if stored and stored['chapters'] else []
    if not chapter_list:
        raise HTTPException(
            status_code=400,
            detail='TAM has never been computed yet — view the TAM Overview tab once first, or pass chapters explicitly.',
        )
    data = _compute_tam_overview_data(db, chapter_list, flow)
    return market_size_store.save_snapshot(db, 'tam', flow, chapter_list, data)


@router.post('/api/trade/tam-global-overview/refresh')
def refresh_tam_overview_endpoint(
    chapters: str | None = Query(None, description='Comma-separated HS 2-digit chapters — omit to reuse the last stored snapshot\'s own scope.'),
    flow: str = Query('M', description='M = imports, X = exports — TAM uses M.'),
    db: Session = Depends(get_db),
):
    return refresh_tam_overview(db, chapters, flow)


@router.get('/api/trade/tam-global-overview/summary')
def tam_global_overview_summary(db: Session = Depends(get_db)):
    """Lightweight figure for the Home page's TAM card: the stored
    snapshot's grand total across every qualifying category and how many
    categories contributed — reads the persisted snapshot only, same
    Comtrade-free contract as sam_overview_summary above."""
    stored = market_size_store.get_snapshot(db, 'tam')
    if not stored:
        return {'computed_at': None, 'total_value': 0.0, 'category_count': 0}
    categories = stored['data'].get('categories', [])
    total_value = sum(category.get('value') or 0.0 for category in categories)
    return {'computed_at': stored['computed_at'], 'total_value': total_value, 'category_count': len(categories)}
