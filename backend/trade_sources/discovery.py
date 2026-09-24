"""Orchestrates the Global Trade Data source-discovery chain — the ONE-TIME
decision (per real country, keyed by CountryReferenceCatalog.country_code)
of which source that country's Global Trade Data view should query going
forward: UN Comtrade, or one of the fallback tiers.

Trigger points (both funnel through `trigger` below):
  1. routers/commercial_structure.py's create_country, the moment a
     country is first added to Commercial Structure — only when its
     resolved reference_country has no trade_data_source yet.
  2. routers/comtrade.py's POST /api/trade/countries/{code}/recheck-source
     — an explicit, unconditional re-run for one country.

Chain, run in order, stopping at the first tier that succeeds:
  1. quick_comtrade_check — fast, synchronous: does Comtrade have a
     reporterCode for this country at all, and does it return real
     category-level data for a recent year/either flow? If yes, `trigger`
     stores 'comtrade' immediately and returns — no fallback chain runs.
  2. If Comtrade has nothing, the rest of the chain runs as a background
     job (background_jobs.py's marker-file convention, one marker per
     country_code) since it's a slow, multi-step external-fetch chain:
       a. tier 1 — this territory's own statistics authority (registry.py)
       b. tier 2 — its administering/parent country's office, territory
          breakout only (registry.py)
       c. tier 3 — US Census/FRED bilateral trade (fred_client.py)
       d. none_found
"""

from datetime import datetime, timezone
from pathlib import Path

from .. import models
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..comtrade import client as comtrade_client
from ..comtrade.countries import list_tracked_countries
from ..database import SessionLocal
from . import fred_client, registry
from .robots import is_allowed

JOB_DIR = Path(__file__).resolve().parent.parent / 'trade_source_discovery_data'

# How many years, newest first, the fast synchronous Comtrade check tries
# before concluding "no data" — small on purpose (this runs inside the
# create_country request/response cycle) — a genuine, slower re-probe
# still happens every time the Global Trade Data page itself is viewed for
# any 'comtrade'-sourced country (see GlobalTradeDataView.jsx's own
# YEAR_PROBE_ATTEMPTS), this is only a coverage smoke test.
COMTRADE_PROBE_YEARS = 3

_BILATERAL_NOTE = (
    'US Census/FRED bilateral trade data — reflects only this territory\'s trade with the United States, '
    'not its total trade with the world. Reported as a single aggregate figure; no HS product-level '
    'breakdown is available.'
)
_NONE_FOUND_NOTE = (
    'No usable trade data source was found for this territory — UN Comtrade, its own/administering '
    'statistics office, and US Census/FRED bilateral series were all checked.'
)


def default_year() -> int:
    # Same "Comtrade lags behind the calendar" lag routers/comtrade.py uses.
    return datetime.now(timezone.utc).year - 1


def marker_path(country_code: str) -> Path:
    return JOB_DIR / f'{country_code.upper()}.job'


def is_discovering(country_code: str) -> bool:
    return is_building(marker_path(country_code))


def discovery_error(country_code: str) -> str | None:
    return get_error(marker_path(country_code))


def _reporter_for(iso2: str) -> dict | None:
    for row in list_tracked_countries():
        if row.get('iso2') == iso2:
            return row
    return None


def quick_comtrade_check(db, country_code: str) -> dict | None:
    """Basic, fast coverage check: does Comtrade have a reporterCode for
    this ISO2 at all, and real category-level rows for a recent year on
    either flow? Returns the matched {name, reporter_code, iso2, iso3} row
    if so, else None. Never raises — a Comtrade outage here is treated the
    same as "no data" (the whole point is not to block country creation on
    a flaky external call; a real re-check is always available via the
    manual recheck endpoint)."""
    reporter = _reporter_for(country_code)
    if not reporter:
        return None
    year = default_year()
    for offset in range(COMTRADE_PROBE_YEARS):
        probe_year = year - offset
        for flow in ('M', 'X'):
            try:
                rows = comtrade_client.fetch_categories(db, reporter['reporter_code'], probe_year, flow)
            except comtrade_client.ComtradeError:
                continue
            if rows:
                return reporter
    return None


def _run_registry_tier(entry: dict | None) -> dict | None:
    """Attempts one tier-1/2 registry entry. Returns the stored-field dict
    if it produced usable data, else None (not registered, robots.txt-
    blocked, or a real-but-not-yet-integrated source — see registry.py)."""
    if not entry:
        return None
    allowed, _reason = is_allowed(entry['check_url'])
    if not allowed:
        return None
    if not entry.get('integrated'):
        # Real, researched source — just not wired to a real fetch
        # adapter yet (see entry['unavailable_reason'] and registry.py's
        # module docstring for why). Framework hook only: a future entry
        # with integrated=True and a 'fetch' callable would be tried here.
        return None
    return entry['fetch'](entry)


def _run_fallback_chain(country_code: str, country_name: str) -> dict:
    """Tiers 1-3, in order. Returns the fields to store on
    CountryReferenceCatalog (trade_data_source/coverage/coverage_note)."""
    tier1, tier2 = registry.tiers_for(country_code)
    for entry in (tier1, tier2):
        result = _run_registry_tier(entry)
        if result:
            return result

    fred_probe = fred_client.probe(country_code, country_name, default_year())
    if fred_probe:
        return {
            'trade_data_source': 'us_census_fred',
            'trade_data_coverage': 'bilateral',
            'trade_data_coverage_note': _BILATERAL_NOTE,
        }

    return {
        'trade_data_source': 'none_found',
        'trade_data_coverage': 'unavailable',
        'trade_data_coverage_note': _NONE_FOUND_NOTE,
    }


def _store_result(country_code: str, fields: dict) -> None:
    db = SessionLocal()
    try:
        row = db.query(models.CountryReferenceCatalog).filter_by(country_code=country_code).first()
        if not row:
            return
        row.trade_data_source = fields['trade_data_source']
        row.trade_data_coverage = fields['trade_data_coverage']
        row.trade_data_coverage_note = fields.get('trade_data_coverage_note')
        row.trade_data_source_checked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
    finally:
        db.close()


def mark_comtrade(country_code: str) -> None:
    """Comtrade already has real data for this country — store that and
    skip the fallback chain entirely (trigger step 2)."""
    _store_result(country_code, {'trade_data_source': 'comtrade', 'trade_data_coverage': 'total', 'trade_data_coverage_note': None})


def _run_job(country_code: str, country_name: str) -> None:
    path = marker_path(country_code)
    try:
        fields = _run_fallback_chain(country_code, country_name)
        _store_result(country_code, fields)
    except Exception as exc:  # noqa: BLE001 - persisted for the recheck UI, not swallowed silently
        mark_error(path, str(exc))
    finally:
        clear_building(path)


def start_fallback_job(background_tasks, country_code: str, country_name: str) -> None:
    path = marker_path(country_code)
    if is_building(path):
        return
    mark_building(path)
    background_tasks.add_task(_run_job, country_code, country_name)


def trigger(background_tasks, db, country_code: str, country_name: str) -> dict:
    """Shared by create_country (only when trade_data_source is still
    unset) and the manual recheck endpoint (always). Does the fast
    Comtrade check synchronously; on empty, kicks off the fallback chain
    in the background rather than blocking the caller. Always returns
    quickly."""
    reporter = quick_comtrade_check(db, country_code)
    if reporter:
        mark_comtrade(country_code)
        return {'status': 'comtrade', 'trade_data_source': 'comtrade'}
    start_fallback_job(background_tasks, country_code, country_name)
    return {'status': 'discovering'}
