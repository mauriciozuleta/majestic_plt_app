"""In-process refresh job (same pattern as accounting_audit_scheduler): ticks every 6 hours and refreshes only the enabled automatic sources whose update frequency elapsed.
A failing source is logged and retried no sooner than 6 hours later; it never raises into the app."""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from ..database import SessionLocal
from . import service

log = logging.getLogger('fuel_prices')
_scheduler = None


def _tick():
    db = SessionLocal()
    try:
        for result in service.refresh_due(db):
            log.info('fuel refresh %s: %s', result.get('source'), 'ok' if result.get('ok') else 'failed')
    except Exception as exc:
        log.warning('fuel refresh tick failed: %s', type(exc).__name__)
    finally:
        db.close()


def start():
    global _scheduler
    db = SessionLocal()
    try:
        service.seed(db)
    finally:
        db.close()
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(_tick, 'interval', hours=6, next_run_time=datetime.now(timezone.utc))
        _scheduler.start()
    return _scheduler
