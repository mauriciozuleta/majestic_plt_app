"""Database operations of the fuel module: seeding, idempotent upserts, imports, scheduled jobs, drop folder, source enablement, series for charts, coverage and staleness."""

import json
import logging
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import geo
from . import models as m
from .sources import ADAPTERS, ATTRIBUTION, SEED_SOURCES, STUB_ADAPTERS, bts_p12, csv_import, iata_regional
from .sources.base import Observation

log = logging.getLogger('fuel_prices')

SEED_EVENTS = [(date(2026, 2, 28), 'Strait of Hormuz closure (per EIA)', 'supply_shock', None)]
# A job is not run again before this many days have passed since its last success
INTERVAL_DAYS = {'daily': 1, 'weekly': 7, 'monthly': 28}
# Data older than this (days, by the newest observation) is flagged stale; weekends/holidays and publication lag are inside these margins
DATA_STALE_DAYS = {'daily': 7, 'weekly': 16, 'monthly': 75}
# A failed job is retried no sooner than this
RETRY_AFTER = timedelta(hours=6)
# TranStats publishes the monthly fuel table about 40 days after month end (page showed data through September on 9 November)
BTS_LAG_DAYS = 45

DROP_DIR = Path(__file__).parent / 'drop' / 'bts_p12'
NATIVE_DRIVERS = ('jet_stocks', 'distillate_stocks', 'refinery_util', 'jet_production', 'jet_exports')
PERIOD_ORDER = {'day': 0, 'week': 1, 'month': 2, 'year': 3}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed(db: Session) -> None:
    """Idempotent. Creates reference data, sources (DISABLED unless verified_ok), events; refreshes source metadata that the user has not signed off; purges restricted sources' data."""
    geo.seed_reference(db)
    existing = {s.id: s for s in db.query(m.FuelSource).all()}
    for row in SEED_SOURCES:
        current = existing.get(row['id'])
        if current is None:
            db.add(m.FuelSource(**row, enabled=row['terms_status'] == 'verified_ok'))
            continue
        for field, value in row.items():
            if field == 'terms_status' and current.terms_signed_off_by and value != 'restricted':
                continue  # never downgrade a status the user signed off
            if field != 'id':
                setattr(current, field, value)
        if current.terms_status == 'restricted':
            current.enabled = False
    for when, title, category, url in SEED_EVENTS:
        if not db.query(m.FuelEvent).filter_by(event_date=when, title=title).first():
            db.add(m.FuelEvent(event_date=when, title=title, category=category, source_url=url))
    for source in db.query(m.FuelSource).filter(m.FuelSource.terms_status == 'restricted'):
        db.query(m.FuelObservation).filter(m.FuelObservation.source_id == source.id).delete()  # restricted content is not kept
    db.commit()
    DROP_DIR.mkdir(parents=True, exist_ok=True)


def upsert(db: Session, observations: list[Observation]) -> dict:
    """Insert or update by (series_id, obs_date[, operator_class]); re-running the same input changes nothing. Native-unit drivers go to fuel_driver_points."""
    prices = [o for o in observations if not o.is_native_driver]
    natives = [o for o in observations if o.is_native_driver]
    a = _upsert_prices(db, prices)
    b = _upsert_natives(db, natives)
    db.commit()
    return {'inserted': a['inserted'] + b['inserted'], 'updated': a['updated'] + b['updated']}


def _upsert_prices(db: Session, observations: list[Observation]) -> dict:
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
            row = m.FuelObservation(series_id=o.series_id, obs_date=o.obs_date, operator_class=o.operator_class, **values)
            db.add(row)
            existing[(o.series_id, o.obs_date, o.operator_class)] = row
            inserted += 1
        elif any(getattr(row, k) != v for k, v in values.items() if k != 'raw_ref'):
            for k, v in values.items():
                setattr(row, k, v)
            updated += 1
    return {'inserted': inserted, 'updated': updated}


def _upsert_natives(db: Session, observations: list[Observation]) -> dict:
    inserted = updated = 0
    if not observations:
        return {'inserted': 0, 'updated': 0}
    series_ids = {o.series_id for o in observations}
    existing = {(r.series_id, r.obs_date): r for r in db.query(m.FuelDriverPoint).filter(m.FuelDriverPoint.series_id.in_(series_ids)).all()}
    for o in observations:
        row = existing.get((o.series_id, o.obs_date))
        if row is None:
            db.add(m.FuelDriverPoint(series_id=o.series_id, driver_code=o.driver_code, obs_date=o.obs_date, period_type=o.period_type, value=o.value_native, unit=o.native_unit,
                                     source_id=o.source_id, raw_ref=o.raw_ref_json()))
            inserted += 1
        elif row.value != o.value_native:
            row.value = o.value_native
            updated += 1
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
            raise ValueError('This source is marked restricted: its terms forbid this use.')
        if source.adapter in STUB_ADAPTERS:
            raise ValueError('This is a stub with no implementation; it cannot be enabled.')
        if source.terms_status != 'verified_ok':
            if not signed_off_by:
                raise ValueError('Terms are not verified_ok: send signed_off_by (your name) to confirm you reviewed the terms.')
            source.terms_signed_off_by = signed_off_by
            source.terms_signed_off_at = _now()
    source.enabled = enabled
    db.commit()
    return source


# ---- scheduled jobs ---------------------------------------------------------------------------------------------------------------------------------------------------------

def _latest_data_date(db: Session, series_id: str | None) -> date | None:
    if not series_id:
        return None
    a = db.query(func.max(m.FuelObservation.obs_date)).filter(m.FuelObservation.series_id == series_id).scalar()
    b = db.query(func.max(m.FuelDriverPoint.obs_date)).filter(m.FuelDriverPoint.series_id == series_id).scalar()
    return max([d for d in (a, b) if d], default=None)


def _run(db: Session, source_id: str, job_key: str) -> m.FuelJobRun:
    row = db.get(m.FuelJobRun, (source_id, job_key))
    if row is None:
        row = m.FuelJobRun(source_id=source_id, job_key=job_key)
        db.add(row)
    return row


def run_job(db: Session, source: m.FuelSource, adapter, job, full: bool = False) -> dict:
    """Backfill the whole history on the first run (or full=True), afterwards only what is new. Never raises: a failure is stored and returned."""
    run = _run(db, source.id, job.key)
    run.frequency = job.frequency
    run.last_attempt_at = _now()
    since = None if full else _latest_data_date(db, job.series_id)
    try:
        obs = adapter.fetch_job(job.key, since)
        result = upsert(db, obs)
        run.last_success_at = _now()
        run.last_error = None
        run.rows_last = len(obs)
        source.last_success_at = run.last_success_at
        source.last_error = None
        db.commit()
        return {'ok': True, 'job': job.key, 'fetched': len(obs), **result, 'incremental': since is not None}
    except Exception as exc:  # a source outage must never crash the app; the message is already sanitised by the adapter
        db.rollback()
        text = f'{type(exc).__name__}: {str(exc)[:300]}'
        run = _run(db, source.id, job.key)
        run.last_attempt_at = _now()
        run.last_error = text
        source = db.get(m.FuelSource, source.id)
        source.last_error = f'{job.key}: {text}'
        db.commit()
        log.warning('fuel job %s/%s failed: %s', source.id, job.key, type(exc).__name__)
        return {'ok': False, 'job': job.key, 'error': text}


def refresh_source(db: Session, source_id: str, full: bool = False) -> dict:
    """Run every job of one automatic source now (the "Download data / Refresh" button)."""
    source = db.get(m.FuelSource, source_id)
    if source is None or not source.enabled or source.adapter not in ADAPTERS:
        return {'ok': False, 'error': 'source missing, disabled or without an automatic adapter'}
    adapter = ADAPTERS[source.adapter]()
    if not adapter.automatic:
        return {'ok': False, 'error': 'not an automatic source'}
    source.last_attempt_at = _now()
    results = [run_job(db, source, adapter, job, full or _latest_data_date(db, job.series_id) is None) for job in adapter.jobs()]
    ok = all(r['ok'] for r in results)
    return {'ok': ok, 'jobs': results, 'fetched': sum(r.get('fetched', 0) for r in results), 'inserted': sum(r.get('inserted', 0) for r in results),
            'updated': sum(r.get('updated', 0) for r in results), 'error': next((r['error'] for r in results if not r['ok']), None)}


def job_due(run: m.FuelJobRun | None, frequency: str, now: datetime) -> bool:
    if run is None or run.last_success_at is None:
        return not (run and run.last_attempt_at and now - run.last_attempt_at < RETRY_AFTER)  # never succeeded: try, but not more than every 6 h
    if run.last_attempt_at and run.last_error and now - run.last_attempt_at < RETRY_AFTER:
        return False
    return now - run.last_success_at >= timedelta(days=INTERVAL_DAYS.get(frequency, 7)) - timedelta(minutes=30)


def refresh_due(db: Session) -> list[dict]:
    """Called by the scheduler on startup (catch-up after downtime, because last-run times are persisted) and every few hours: runs each enabled automatic source's jobs that are due."""
    out = []
    now = _now()
    for source in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True)).all():
        if source.adapter not in ADAPTERS or not ADAPTERS[source.adapter].automatic:
            continue
        adapter = ADAPTERS[source.adapter]()
        for job in adapter.jobs():
            if job_due(db.get(m.FuelJobRun, (source.id, job.key)), job.frequency, now):
                out.append({'source': source.id, **run_job(db, source, adapter, job)})
    out.extend(scan_drop_folder(db))
    return out


# ---- BTS monthly drop folder --------------------------------------------------------------------------------------------------------------------------------------------------

def scan_drop_folder(db: Session) -> list[dict]:
    """Import every .csv in backend/fuel_prices/drop/bts_p12/ using column_map.json from the same folder; imported files move to processed/, rejected ones to failed/ with a .error.txt."""
    source = db.get(m.FuelSource, 'bts_p12')
    if source is None or not source.enabled or not DROP_DIR.exists():
        return []
    files = sorted(DROP_DIR.glob('*.csv'))
    if not files:
        return []
    out = []
    map_path = DROP_DIR / 'column_map.json'
    try:
        column_map = json.loads(map_path.read_text(encoding='utf-8')) if map_path.exists() else None
    except ValueError as exc:
        return [{'source': 'bts_p12', 'ok': False, 'error': f'column_map.json is not valid JSON: {exc}'}]
    if column_map is None:
        return [{'source': 'bts_p12', 'ok': False, 'error': 'put a column_map.json next to the file (explicit column mapping is required for automatic import)'}]
    for path in files:
        run = _run(db, 'bts_p12', 'drop_folder')
        run.frequency, run.last_attempt_at = 'monthly', _now()
        try:
            obs, errors = bts_p12.parse(path.read_text(encoding='utf-8-sig', errors='replace'), column_map)
            if errors:
                raise ValueError('; '.join(errors)[:300])
            result = upsert(db, obs)
            dest = DROP_DIR / 'processed'
            dest.mkdir(exist_ok=True)
            shutil.move(str(path), dest / f'{datetime.now():%Y%m%d-%H%M%S}_{path.name}')
            run.last_success_at, run.last_error, run.rows_last = _now(), None, len(obs)
            source.last_success_at, source.last_error = run.last_success_at, None
            db.commit()
            out.append({'source': 'bts_p12', 'ok': True, 'file': path.name, 'months': len(obs), **result})
        except Exception as exc:
            db.rollback()
            dest = DROP_DIR / 'failed'
            dest.mkdir(exist_ok=True)
            target = dest / path.name
            shutil.move(str(path), target)
            target.with_name(target.name + '.error.txt').write_text(str(exc), encoding='utf-8')
            run = _run(db, 'bts_p12', 'drop_folder')
            run.last_attempt_at, run.last_error = _now(), f'{path.name}: {str(exc)[:250]}'
            db.get(m.FuelSource, 'bts_p12').last_error = run.last_error
            db.commit()
            out.append({'source': 'bts_p12', 'ok': False, 'file': path.name, 'error': str(exc)[:300]})
    return out


# ---- views ------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def sources_view(db: Session) -> list[dict]:
    counts = dict(db.query(m.FuelObservation.source_id, func.count()).group_by(m.FuelObservation.source_id).all())
    for source_id, n in db.query(m.FuelDriverPoint.source_id, func.count()).group_by(m.FuelDriverPoint.source_id).all():
        counts[source_id] = counts.get(source_id, 0) + n
    return [{'id': s.id, 'name': s.name, 'url': s.url, 'license_terms_url': s.license_terms_url, 'terms_status': s.terms_status, 'enabled': s.enabled,
             'terms_signed_off_by': s.terms_signed_off_by, 'auth_type': s.auth_type, 'rate_limit_notes': s.rate_limit_notes, 'update_frequency': s.update_frequency,
             'coverage': s.coverage, 'notes': s.notes, 'automatic': bool(s.adapter in ADAPTERS and ADAPTERS[s.adapter].automatic), 'last_success_at': s.last_success_at,
             'last_error': s.last_error, 'observations': counts.get(s.id, 0), 'attribution': ATTRIBUTION.get(s.id), 'drop_folder': str(DROP_DIR) if s.id == 'bts_p12' else None}
            for s in db.query(m.FuelSource).order_by(m.FuelSource.name).all()]


def series(db: Session, *, kind: str = 'price', country=None, airport=None, region=None, operator_class='scheduled', driver=None, date_from=None, date_to=None,
           period: str | None = None, source_id: str | None = None) -> dict:
    """Points of one series for charting: price series are picked by place+class (finest enabled series wins); drivers by code. Returns the series id used."""
    enabled = [s.id for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True))]
    if kind == 'driver' and driver in NATIVE_DRIVERS:
        return _native_series(db, driver, enabled, date_from, date_to, period)
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
    best = sorted(by_series.items(), key=lambda kv: (PERIOD_ORDER.get(kv[1][0].period_type, 9), -len(kv[1])))[0]
    pts = best[1]
    mix: dict[str, int] = {}
    for r in pts:
        mix[r.quality] = mix.get(r.quality, 0) + 1
    return {'series_id': best[0], 'period_type': pts[0].period_type, 'price_basis': pts[0].price_basis, 'source': pts[0].source_id, 'attribution': ATTRIBUTION.get(pts[0].source_id),
            'quality_mix': mix, 'points': [{'date': r.obs_date.isoformat(), 'value': round(r.value_usd_per_gal, 5)} for r in pts]}


def _native_series(db: Session, driver: str, enabled: list[str], date_from, date_to, period) -> dict:
    q = db.query(m.FuelDriverPoint).filter(m.FuelDriverPoint.driver_code == driver, m.FuelDriverPoint.source_id.in_(enabled))
    if date_from:
        q = q.filter(m.FuelDriverPoint.obs_date >= date_from)
    if date_to:
        q = q.filter(m.FuelDriverPoint.obs_date <= date_to)
    rows = q.order_by(m.FuelDriverPoint.obs_date).all()
    if not rows:
        return {'series_id': None, 'points': [], 'quality_mix': {}}
    return {'series_id': rows[0].series_id, 'period_type': rows[0].period_type, 'unit': rows[0].unit, 'source': rows[0].source_id, 'attribution': ATTRIBUTION.get(rows[0].source_id),
            'quality_mix': {'observed': len(rows)}, 'points': [{'date': r.obs_date.isoformat(), 'value': r.value} for r in rows]}


def _job_status(source: m.FuelSource, run: m.FuelJobRun | None, frequency: str, latest: date | None, series_id: str | None, today: date, now: datetime) -> tuple[str, str]:
    if not source.enabled:
        return 'disabled', 'source disabled'
    if run is None or run.last_success_at is None:
        return ('error', run.last_error or 'never succeeded') if run and run.last_error else ('never_run', 'has not run yet')
    if run.last_error and run.last_attempt_at and run.last_attempt_at > run.last_success_at:
        return 'error', f'last attempt failed: {run.last_error}'
    if now - run.last_success_at > timedelta(days=INTERVAL_DAYS.get(frequency, 7) * 2 + 1):
        return 'stale', f'job has not succeeded for {(now - run.last_success_at).days} days (runs every {INTERVAL_DAYS.get(frequency, 7)})'
    data_frequency = 'monthly' if source.id == 'bts_p12' else frequency
    if series_id and latest and (today - latest).days > DATA_STALE_DAYS.get(data_frequency, 16):
        return 'stale', f'newest data point is {(today - latest).days} days old'
    return 'ok', ''


def bts_reminder(db: Session, today: date | None = None) -> dict | None:
    """Monthly reminder: when the newest month of imported BTS P-12(a) data is older than the month TranStats should have published by now."""
    source = db.get(m.FuelSource, 'bts_p12')
    if source is None or not source.enabled:
        return None
    today = today or date.today()
    expected = (today - timedelta(days=BTS_LAG_DAYS)).replace(day=1)
    latest = db.query(func.max(m.FuelObservation.obs_date)).filter(m.FuelObservation.source_id == 'bts_p12').scalar()
    if latest and latest >= expected:
        return None
    return {'source': 'bts_p12', 'message': f'BTS data through {expected:%B %Y} is pending. Automatic checks continue; see the source status for download errors.', 'expected_through': expected.isoformat(),
            'latest_imported': latest.isoformat() if latest else None, 'url': 'https://www.transtats.bts.gov/fuel.asp', 'drop_folder': str(DROP_DIR)}


def coverage(db: Session, today: date | None = None) -> dict:
    """Which places hold observed data (enabled sources), the state of every scheduled job (with stale warnings), reminders, and the sources that are off."""
    today = today or date.today()
    now = _now()
    enabled = [s.id for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True))]
    rows = (db.query(m.FuelObservation.geo_level, m.FuelObservation.country_iso2, m.FuelObservation.airport_iata, m.FuelObservation.region_code,
                     m.FuelObservation.operator_class, func.count(), func.max(m.FuelObservation.obs_date))
            .filter(m.FuelObservation.series_kind == 'price', m.FuelObservation.source_id.in_(enabled))
            .group_by(m.FuelObservation.geo_level, m.FuelObservation.country_iso2, m.FuelObservation.airport_iata, m.FuelObservation.region_code,
                      m.FuelObservation.operator_class).all())
    places = [{'geo_level': g, 'country': c, 'airport': a, 'region': r, 'operator_class': o, 'observations': n, 'latest': d.isoformat()} for g, c, a, r, o, n, d in rows]
    jobs = []
    for source in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True)):
        if source.adapter in ADAPTERS and ADAPTERS[source.adapter].automatic:
            for job in ADAPTERS[source.adapter]().jobs():
                run = db.get(m.FuelJobRun, (source.id, job.key))
                latest = _latest_data_date(db, job.series_id)
                status, why = _job_status(source, run, job.frequency, latest, job.series_id, today, now)
                jobs.append({'source': source.id, 'job': job.key, 'label': job.label, 'frequency': job.frequency, 'status': status, 'detail': why, 'latest_data': latest.isoformat() if latest else None,
                             'last_success_at': run.last_success_at if run else None, 'last_error': run.last_error if run else None})
    reminders = [r for r in (bts_reminder(db, today),) if r]
    disabled = [{'id': s.id, 'name': s.name, 'terms_status': s.terms_status} for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(False))]
    return {'places': places, 'jobs': jobs, 'reminders': reminders, 'stale': [j for j in jobs if j['status'] in ('stale', 'error')], 'disabled_sources': disabled,
            'countries_total': db.query(m.FuelCountry).count()}
