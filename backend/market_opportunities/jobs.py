"""Running a comparison as a background job the caller polls (the AI judge and the web research can take minutes). One job per (source, targets) at a time. The state lives in
memory — a backend restart forgets a job that was running, and the comparison simply has not been saved (nothing half-written: a run is saved in one step at its end)."""

import threading
from datetime import datetime, timezone

from . import engine

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def job_key(source_country: str, target_countries: list[str]) -> str:
    return f"{source_country}>{','.join(sorted(target_countries))}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status(source_country: str, target_countries: list[str]) -> dict:
    with _lock:
        return dict(_jobs.get(job_key(source_country, target_countries)) or {'status': 'idle'})


def _run(key: str, source_country: str, target_countries: list[str], force: bool, allow_ai: bool, allow_research: bool, session_factory, hooks: dict) -> None:
    db = session_factory()
    try:
        result = engine.get_or_compute(db, source_country, target_countries, force=force, allow_ai=allow_ai, allow_research=allow_research, **hooks)
        state = {'status': 'done', 'finished_at': _now(), 'result': result}
    except Exception as error:  # noqa: BLE001 — shown to the person
        state = {'status': 'error', 'finished_at': _now(), 'error': str(error)}
    finally:
        db.close()
    with _lock:
        _jobs[key] = {**_jobs[key], **state}


def start(source_country: str, target_countries: list[str], *, force: bool, allow_ai: bool, allow_research: bool, session_factory=None, wait: bool = False, **hooks) -> dict:
    """Starts the job (or reports the one already running). With `wait`, runs it in this thread and returns when it is done."""
    from ..database import SessionLocal

    key = job_key(source_country, target_countries)
    with _lock:
        if (_jobs.get(key) or {}).get('status') == 'building':
            return dict(_jobs[key])
        _jobs[key] = {'status': 'building', 'started_at': _now()}
    args = (key, source_country, target_countries, force, allow_ai, allow_research, session_factory or SessionLocal, hooks)
    if wait:
        _run(*args)
    else:
        threading.Thread(target=_run, args=args, name=f'market-opportunities-{key[:40]}', daemon=True).start()
    return status(source_country, target_countries)
