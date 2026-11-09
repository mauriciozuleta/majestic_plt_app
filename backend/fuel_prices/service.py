"""Database operations of the fuel module: seeding, idempotent upserts, imports, refresh jobs, source enablement, series for charts."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import geo
from . import models as m
from .sources import ADAPTERS, SEED_SOURCES, bts_p12, csv_import, iata_regional
from .sources.base import Observation

log = logging.getLogger('fuel_prices')

SEED_EVENTS = [(date(2026, 2, 28), 'Strait of Hormuz closure (per EIA)', 'supply_shock', None)]
# a source is not polled again before this many days have passed since its last success
FREQUENCY_DAYS = {'daily': 1, 'weekly': 7, 'monthly': 28}


def seed(db: Session) -> None:
    """Idempotent. Sources land DISABLED (only the user's own CSV channel, terms verified_ok, starts enabled)."""
    geo.seed_reference(db)
    existing = {s.id for s in db.query(m.FuelSource.id).all()}
    for row in SEED_SOURCES:
        if row['id'] not in existing:
            db.add(m.FuelSource(**row, enabled=row['terms_status'] == 'verified_ok'))
    for when, title, category, url in SEED_EVENTS:
        if not db.query(m.FuelEvent).filter_by(event_date=when, title=title).first():
            db.add(m.FuelEvent(event_date=when, title=title, category=category, source_url=url))
    db.commit()


def upsert(db: Session, observations: list[Observation]) -> dict:
    """Insert or update by (series_id, obs_date, operator_class); re-running the same input changes nothing."""
    inserted = updated = 0
    if not observations:
        return {'inserted': 0, 'updated': 0}
    series_ids = {o.series_id for o in observations}
    existing = {(r.series_id, r.obs_date, r.operator_class): r for r in db.query(m.FuelObservation).filter(m.FuelObservation.series_id.in_(series_ids)).all()}
    for o in observations:
        values = dict(series_kind=o.series_kind, driver_code=o.driver_code, period_type=o.period_type, value_usd_per_gal=o.value_usd_per_gal, value_original=o.value_original,
                      unit_original=o.unit_original, currency_original=o.currency_original, geo_level=o.geo_level, region_code=o.region_code, country_iso2=o.country_iso2,
                      airport_iata=o.airport_iata, price_basis=o.price_basis, source_id=o.source_id, raw_ref=o.raw_ref_json(), quality=o.quality, confidence=o.confidence)
        row = existing.get((o.series_id, o.obs_date, o.operator_class))
        if row is None:
            db.add(m.FuelObservation(series_id=o.series_id, obs_date=o.obs_date, operator_class=o.operator_class, **values))
            inserted += 1
        elif any(getattr(row, k) != v for k, v in values.items() if k != 'raw_ref'):
            for k, v in values.items():
                setattr(row, k, v)
            updated += 1
    db.commit()
    return {'inserted': inserted, 'updated': updated}


class SourceDisabled(Exception):
    pass


def _require_enabled(db: Session, source_id: str) -> m.FuelSource:
    source = db.get(m.FuelSource, source_id)
    if source is None:
        raise KeyError(source_id)
    if not source.enabled:
        raise SourceDisabled(f'Source {source_id} is disabled (terms status: {source.terms_status}). Enable it explicitly first.')
    return source


def import_csv(db: Session, text: str, source_id: str = 'manual_csv') -> dict:
    _require_enabled(db, source_id)
    obs, errors = csv_import.parse(text, source_id)
    if errors:
        return {'ok': False, 'errors': errors[:50], 'error_count': len(errors)}
    return {'ok': True, **upsert(db, obs)}


def import_iata(db: Session, text: str) -> dict:
    _require_enabled(db, 'iata_regional')
    obs, errors, info = iata_regional.parse(text)
    if errors:
        return {'ok': False, 'errors': errors[:50], 'error_count': len(errors)}
    return {'ok': True, **upsert(db, obs), **info}


def import_bts(db: Session, text: str, column_map: dict | None = None) -> dict:
    _require_enabled(db, 'bts_p12')
    obs, errors = bts_p12.parse(text, column_map)
    if errors:
        return {'ok': False, 'errors': errors}
    return {'ok': True, **upsert(db, obs), 'months': len(obs)}


def set_enabled(db: Session, source_id: str, enabled: bool, signed_off_by: str | None = None) -> m.FuelSource:
    """Enabling a source whose terms are not verified_ok needs the user's explicit sign-off name, which is stored with the time."""
    source = db.get(m.FuelSource, source_id)
    if source is None:
        raise KeyError(source_id)
    if enabled:
        if source.terms_status == 'restricted':
            raise ValueError('This source is marked restricted: its terms forbid this use. Change the terms status first if that is wrong.')
        if source.terms_status != 'verified_ok':
            if not signed_off_by:
                raise ValueError('Terms are not verified_ok: send signed_off_by (your name) to confirm you reviewed the terms.')
            source.terms_signed_off_by = signed_off_by
            source.terms_signed_off_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if source.adapter in ('platts_stub', 'argus_stub', 'airnav_stub'):
            raise ValueError('This is a stub with no implementation; it cannot be enabled.')
    source.enabled = enabled
    db.commit()
    return source


def refresh_source(db: Session, source_id: str, full: bool = False) -> dict:
    """Fetch one automatic source and upsert. Never raises: a failure is stored in last_error and returned."""
    source = db.get(m.FuelSource, source_id)
    if source is None or not source.enabled or source.adapter not in ADAPTERS:
        return {'ok': False, 'error': 'source missing, disabled or without an automatic adapter'}
    adapter = ADAPTERS[source.adapter]()
    if not adapter.automatic:
        return {'ok': False, 'error': 'not an automatic source'}
    source.last_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None)
    since = None
    if not full:
        newest = db.query(func.max(m.FuelObservation.obs_date)).filter(m.FuelObservation.source_id == source_id).scalar()
        since = newest - timedelta(days=45) if newest else None  # overlap so revisions are picked up
    try:
        obs = adapter.fetch(since)
        result = upsert(db, obs)
        source.last_success_at = datetime.now(timezone.utc).replace(tzinfo=None)
        source.last_error = None
        db.commit()
        return {'ok': True, **result, 'fetched': len(obs)}
    except Exception as exc:  # a source outage must never crash the app
        db.rollback()
        source = db.get(m.FuelSource, source_id)
        source.last_error = f'{type(exc).__name__}: {str(exc)[:300]}'
        db.commit()
        log.warning('fuel source %s failed: %s', source_id, type(exc).__name__)
        return {'ok': False, 'error': source.last_error}


def refresh_due(db: Session) -> list[dict]:
    """Called by the scheduler: refreshes every enabled automatic source whose update frequency has elapsed."""
    out = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for source in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True)).all():
        if source.adapter not in ADAPTERS or not ADAPTERS[source.adapter].automatic:
            continue
        days = FREQUENCY_DAYS.get(source.update_frequency or '', 7)
        if source.last_success_at and now - source.last_success_at < timedelta(days=days):
            continue
        if source.last_attempt_at and now - source.last_attempt_at < timedelta(hours=6):
            continue  # back off after a failure
        out.append({'source': source.id, **refresh_source(db, source.id)})
    return out


def sources_view(db: Session) -> list[dict]:
    counts = dict(db.query(m.FuelObservation.source_id, func.count()).group_by(m.FuelObservation.source_id).all())
    return [{'id': s.id, 'name': s.name, 'url': s.url, 'license_terms_url': s.license_terms_url, 'terms_status': s.terms_status, 'enabled': s.enabled,
             'terms_signed_off_by': s.terms_signed_off_by, 'auth_type': s.auth_type, 'rate_limit_notes': s.rate_limit_notes, 'update_frequency': s.update_frequency,
             'coverage': s.coverage, 'notes': s.notes, 'automatic': bool(s.adapter in ADAPTERS and ADAPTERS[s.adapter].automatic), 'last_success_at': s.last_success_at,
             'last_error': s.last_error, 'observations': counts.get(s.id, 0)} for s in db.query(m.FuelSource).order_by(m.FuelSource.name).all()]


def series(db: Session, *, kind: str = 'price', country=None, airport=None, region=None, operator_class='scheduled', driver=None, date_from=None, date_to=None,
           period: str | None = None, source_id: str | None = None) -> dict:
    """Points of one series for charting: price series are picked by place+class (finest enabled series wins); drivers by code. Returns the series id used."""
    enabled = [s.id for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True))]
    q = db.query(m.FuelObservation).filter(m.FuelObservation.series_kind == kind, m.FuelObservation.source_id.in_(enabled))
    if kind == 'driver':
        q = q.filter(m.FuelObservation.driver_code == driver)
    else:
        q = q.filter(m.FuelObservation.operator_class == operator_class)
        if airport:
            q = q.filter(m.FuelObservation.geo_level == 'airport', m.FuelObservation.airport_iata == airport.upper())
        elif country:
            q = q.filter(m.FuelObservation.geo_level == 'country', m.FuelObservation.country_iso2 == country.upper())
        elif region:
            q = q.filter(m.FuelObservation.geo_level == 'region', m.FuelObservation.region_code == region.upper())
        else:
            q = q.filter(m.FuelObservation.geo_level == 'global')
    if source_id:
        q = q.filter(m.FuelObservation.source_id == source_id)
    if date_from:
        q = q.filter(m.FuelObservation.obs_date >= date_from)
    if date_to:
        q = q.filter(m.FuelObservation.obs_date <= date_to)
    rows = q.order_by(m.FuelObservation.obs_date).all()
    if not rows:
        return {'series_id': None, 'points': [], 'quality_mix': {}}
    by_series: dict[str, list] = {}
    for r in rows:
        by_series.setdefault(r.series_id, []).append(r)
    if period:
        by_series = {k: v for k, v in by_series.items() if v[0].period_type == period} or by_series
    # prefer the finest period, then the longest series
    best = sorted(by_series.items(), key=lambda kv: (PERIOD_ORDER.get(kv[1][0].period_type, 9), -len(kv[1])))[0]
    pts = best[1]
    mix: dict[str, int] = {}
    for r in pts:
        mix[r.quality] = mix.get(r.quality, 0) + 1
    return {'series_id': best[0], 'period_type': pts[0].period_type, 'price_basis': pts[0].price_basis, 'source': pts[0].source_id, 'quality_mix': mix,
            'points': [{'date': r.obs_date.isoformat(), 'value': round(r.value_usd_per_gal, 5)} for r in pts]}


PERIOD_ORDER = {'day': 0, 'week': 1, 'month': 2}


def coverage(db: Session) -> dict:
    """Which countries/airports/regions hold observed data (from enabled sources) vs the sources that are off."""
    enabled = [s.id for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True))]
    rows = (db.query(m.FuelObservation.geo_level, m.FuelObservation.country_iso2, m.FuelObservation.airport_iata, m.FuelObservation.region_code,
                     m.FuelObservation.operator_class, func.count(), func.max(m.FuelObservation.obs_date))
            .filter(m.FuelObservation.series_kind == 'price', m.FuelObservation.source_id.in_(enabled))
            .group_by(m.FuelObservation.geo_level, m.FuelObservation.country_iso2, m.FuelObservation.airport_iata, m.FuelObservation.region_code,
                      m.FuelObservation.operator_class).all())
    places = [{'geo_level': g, 'country': c, 'airport': a, 'region': r, 'operator_class': o, 'observations': n, 'latest': d.isoformat()} for g, c, a, r, o, n, d in rows]
    disabled = [{'id': s.id, 'name': s.name, 'terms_status': s.terms_status} for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(False))]
    return {'places': places, 'disabled_sources': disabled, 'countries_total': db.query(m.FuelCountry).count()}
