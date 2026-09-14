from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..accounting_auditor import run_audit
from .settings import _get_or_create_settings

router = APIRouter()

MIN_INTERVAL_DAYS = 1
MAX_INTERVAL_DAYS = 90


def _run_summary(run: models.AccountingAuditRun):
    return {
        'id': run.id,
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'status': run.status,
        'scope_company_id': run.scope_company_id,
        'triggered_by': run.triggered_by,
        'entries_checked': run.entries_checked,
        'findings_count': run.findings_count,
        'error_message': run.error_message,
    }


def _finding_out(finding: models.AccountingAuditFinding):
    return {
        'id': finding.id,
        'company_id': finding.company_id,
        'entry_id': finding.entry_id,
        'severity': finding.severity,
        'code': finding.code,
        'message': finding.message,
    }


@router.get('/accounting-audit/settings')
def get_audit_settings(db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)
    return {
        'enabled': bool(settings.audit_enabled),
        'interval_days': settings.audit_interval_days or 7,
        'scope_company_id': settings.audit_scope_company_id,
        'last_run_at': settings.audit_last_run_at,
    }


@router.patch('/accounting-audit/settings')
def set_audit_settings(payload: dict, db: Session = Depends(get_db)):
    settings = _get_or_create_settings(db)

    if 'enabled' in payload:
        if not isinstance(payload['enabled'], bool):
            raise HTTPException(status_code=400, detail='enabled must be a boolean')
        settings.audit_enabled = payload['enabled']

    if 'interval_days' in payload:
        interval_days = payload['interval_days']
        if not isinstance(interval_days, int) or not (MIN_INTERVAL_DAYS <= interval_days <= MAX_INTERVAL_DAYS):
            raise HTTPException(status_code=400, detail=f'interval_days must be an integer between {MIN_INTERVAL_DAYS} and {MAX_INTERVAL_DAYS}')
        settings.audit_interval_days = interval_days

    if 'scope_company_id' in payload:
        scope_company_id = payload['scope_company_id']
        if scope_company_id is not None and not isinstance(scope_company_id, str):
            raise HTTPException(status_code=400, detail='scope_company_id must be a string or null')
        settings.audit_scope_company_id = scope_company_id or None

    db.commit()
    return {
        'enabled': bool(settings.audit_enabled),
        'interval_days': settings.audit_interval_days or 7,
        'scope_company_id': settings.audit_scope_company_id,
        'last_run_at': settings.audit_last_run_at,
    }


@router.post('/accounting-audit/run-now')
def trigger_audit_run(payload: dict | None = None, db: Session = Depends(get_db)):
    scope_company_id = (payload or {}).get('scope_company_id')
    run = run_audit(db, scope_company_id=scope_company_id, triggered_by='manual')
    settings = _get_or_create_settings(db)
    settings.audit_last_run_at = run.finished_at
    db.commit()
    return _run_summary(run)


@router.get('/accounting-audit/runs')
def list_audit_runs(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    runs = (
        db.query(models.AccountingAuditRun)
        .order_by(models.AccountingAuditRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_run_summary(run) for run in runs]


@router.get('/accounting-audit/runs/{run_id}')
def get_audit_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(models.AccountingAuditRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail='Audit run not found')
    findings = (
        db.query(models.AccountingAuditFinding)
        .filter_by(run_id=run_id)
        .order_by(models.AccountingAuditFinding.severity.asc(), models.AccountingAuditFinding.company_id.asc())
        .all()
    )
    return {**_run_summary(run), 'findings': [_finding_out(finding) for finding in findings]}
