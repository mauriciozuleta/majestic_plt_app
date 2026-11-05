"""Marker-file helpers for long-running AI research jobs (country profile,
competitiveness analysis) that must survive the triggering HTTP request
ending — the frontend navigating away, a component unmounting, even the
browser tab closing, none of that should stop a job that's already running
server-side via FastAPI's BackgroundTasks. Status is tracked as sibling
files next to the job's real output file rather than in-memory, so it also
survives a backend restart mid-job (the job itself would still be lost, but
at least GET won't report a phantom "building" state forever)."""


import time

_SERVER_STARTED = time.time()


def is_building(base_path):
    """A marker written before this server process started belongs to a job that died with the previous process (a restart kills BackgroundTasks), so it is
    removed instead of reporting a phantom "building" state forever."""
    marker = base_path.with_suffix(base_path.suffix + '.building')
    if not marker.exists():
        return False
    if marker.stat().st_mtime < _SERVER_STARTED:
        marker.unlink(missing_ok=True)
        return False
    return True


def mark_building(base_path):
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.with_suffix(base_path.suffix + '.building').write_text('', encoding='utf-8')
    get_error_path(base_path).unlink(missing_ok=True)


def clear_building(base_path):
    base_path.with_suffix(base_path.suffix + '.building').unlink(missing_ok=True)


def get_error_path(base_path):
    return base_path.with_suffix(base_path.suffix + '.error')


def mark_error(base_path, message):
    get_error_path(base_path).write_text(message, encoding='utf-8')


def get_error(base_path):
    error_path = get_error_path(base_path)
    return error_path.read_text(encoding='utf-8') if error_path.exists() else None
