"""
In-process background scheduler for the accounting auditor's "Accounting
Health Check" — this app has no other job runner (no cron, no task queue),
but the backend is already a long-running uvicorn process, so an in-process
APScheduler is the simplest way to run something on a recurring interval
without a browser tab having to stay open.

The scheduler itself just ticks once an hour and asks "is a run due?" — it
does not reschedule itself when settings change, so toggling the interval
or turning the check on/off in Settings takes effect on the next tick
rather than needing a backend restart.
"""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .accounting_auditor import run_audit
from .database import SessionLocal
from . import models

CHECK_INTERVAL_MINUTES = 60

_scheduler = None


def _is_run_due(settings):
    if not settings.audit_enabled:
        return False
    if not settings.audit_last_run_at:
        return True
    try:
        last_run = datetime.fromisoformat(settings.audit_last_run_at)
    except (TypeError, ValueError):
        return True
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    interval_days = settings.audit_interval_days or 7
    return datetime.now(timezone.utc) >= last_run + timedelta(days=interval_days)


def _tick():
    db = SessionLocal()
    try:
        settings = db.query(models.PortfolioSettings).filter_by(id='singleton').first()
        if not settings or not _is_run_due(settings):
            return
        run = run_audit(db, scope_company_id=settings.audit_scope_company_id, triggered_by='scheduled')
        settings.audit_last_run_at = run.finished_at
        db.commit()
    finally:
        db.close()


def start_accounting_audit_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_tick, 'interval', minutes=CHECK_INTERVAL_MINUTES, next_run_time=datetime.now(timezone.utc))
    _scheduler.start()
    return _scheduler
