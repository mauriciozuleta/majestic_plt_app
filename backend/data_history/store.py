"""The data history: an append-only record of every state a stored dataset has had, in its OWN SQLite file (`majestic_history.db` next to
`majestic_plt.db`, kept out of git) so a damaged or restored main database never takes the history with it, and the history growing never bloats the
main file. Plain `sqlite3`, no ORM: this module must not depend on the app's models.

Two tables:
  data_versions  one row per (scope, version): who/when/why, a content hash (an identical refresh adds no version), the data gzip-compressed.
  held_updates   a refresh that looked worse than what is stored (empty, far fewer rows ...) waits here until a person approves or rejects it.

A "scope" names one dataset: `snapshot:<source key>` (a product catalog), `market_size:sam|tam`, `file:<path under backend/>` (a tariff file, a profile).
"""

import contextlib
import contextvars
import gzip
import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / 'majestic_history.db'

# Retention: the newest KEEP_LAST versions of a scope, plus the newest of each of the last KEEP_MONTHS calendar months, plus pinned ones and the latest.
# Big files (a 12 MB tariff) keep fewer.
KEEP_LAST, KEEP_MONTHS = 30, 24
BIG_PAYLOAD_BYTES = 1_000_000
KEEP_LAST_BIG, KEEP_MONTHS_BIG = 5, 6

_path: Path = Path(os.environ.get('MAJESTIC_HISTORY_DB') or DEFAULT_PATH)
_lock = threading.RLock()
_actor = contextvars.ContextVar('data_history_actor', default='app')

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    kind TEXT NOT NULL,            -- json | file | deleted
    payload BLOB NOT NULL,
    raw_size INTEGER NOT NULL,
    stats TEXT NOT NULL DEFAULT '{}',
    pinned INTEGER NOT NULL DEFAULT 0,
    UNIQUE (scope, version)
);
CREATE INDEX IF NOT EXISTS ix_data_versions_scope ON data_versions (scope, version);
CREATE TABLE IF NOT EXISTS held_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    findings TEXT NOT NULL,
    stats TEXT NOT NULL DEFAULT '{}',
    meta TEXT NOT NULL DEFAULT '{}',
    payload BLOB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected | superseded
    resolved_at TEXT,
    resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_held_updates_status ON held_updates (status, scope);
"""


class HeldForApproval(Exception):
    """A refresh looked worse than the stored data and was parked in `held_updates` instead of being saved."""

    def __init__(self, scope: str, held_id: int, findings: list[str]):
        self.scope, self.held_id, self.findings = scope, held_id, findings
        super().__init__(f'Update of {scope} held for approval: {"; ".join(findings)}. Review it in Settings ▸ Data history.')


def use_database(path: Path | str | None) -> None:
    """Points the history at another file (tests, or a relocation). None goes back to the default."""
    global _path
    _path = Path(path) if path else Path(os.environ.get('MAJESTIC_HISTORY_DB') or DEFAULT_PATH)


def database_path() -> Path:
    return _path


@contextlib.contextmanager
def acting_as(actor: str):
    """Names who is causing the writes inside the block ('user', 'assistant', 'agent:<task>', 'restore' ...)."""
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)


def current_actor() -> str:
    return _actor.get()


@contextlib.contextmanager
def _connect():
    with _lock:
        _path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript(SCHEMA)
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode(kind: str, data) -> bytes:
    """json: any JSON-able value; file: bytes; deleted: a JSON note."""
    raw = data if kind == 'file' else json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return raw


def _decode(kind: str, raw: bytes):
    return raw if kind == 'file' else json.loads(raw.decode('utf-8'))


def _summary(row: sqlite3.Row) -> dict:
    return {'scope': row['scope'], 'version': row['version'], 'created_at': row['created_at'], 'actor': row['actor'], 'reason': row['reason'], 'kind': row['kind'],
            'raw_size': row['raw_size'], 'pinned': bool(row['pinned']), 'stats': json.loads(row['stats'] or '{}')}


def record(scope: str, kind: str, data, *, reason: str, actor: str | None = None, stats: dict | None = None) -> dict | None:
    """Adds the new state of a dataset as its next version. Returns None (and adds nothing) when it is identical to the latest version."""
    raw = _encode(kind, data)
    digest = hashlib.sha256(kind.encode() + b'\0' + raw).hexdigest()
    with _connect() as connection:
        latest = connection.execute('SELECT version, content_hash FROM data_versions WHERE scope = ? ORDER BY version DESC LIMIT 1', (scope,)).fetchone()
        if latest and latest['content_hash'] == digest:
            return None
        version = (latest['version'] if latest else 0) + 1
        connection.execute(
            'INSERT INTO data_versions (scope, version, created_at, actor, reason, content_hash, kind, payload, raw_size, stats) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (scope, version, _now(), actor or current_actor(), reason, digest, kind, gzip.compress(raw, 6), len(raw), json.dumps(stats or {})),
        )
        row = connection.execute('SELECT * FROM data_versions WHERE scope = ? AND version = ?', (scope, version)).fetchone()
        result = _summary(row)
        _prune(connection, scope)
    return result


def record_deleted(scope: str, *, reason: str, actor: str | None = None, stats: dict | None = None) -> dict | None:
    """Final version of a dataset that was deleted. The version before it still holds the data."""
    return record(scope, 'deleted', {'deleted': True}, reason=reason, actor=actor, stats=stats)


def latest(scope: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute('SELECT * FROM data_versions WHERE scope = ? ORDER BY version DESC LIMIT 1', (scope,)).fetchone()
        return _summary(row) if row else None


def versions(scope: str) -> list[dict]:
    with _connect() as connection:
        return [_summary(row) for row in connection.execute('SELECT * FROM data_versions WHERE scope = ? ORDER BY version DESC', (scope,))]


def load(scope: str, version: int | None = None):
    """(kind, data) of one version (default: the latest). KeyError if there is none."""
    with _connect() as connection:
        query, args = ('SELECT kind, payload FROM data_versions WHERE scope = ? AND version = ?', (scope, version)) if version is not None else (
            'SELECT kind, payload FROM data_versions WHERE scope = ? ORDER BY version DESC LIMIT 1', (scope,))
        row = connection.execute(query, args).fetchone()
    if row is None:
        raise KeyError(f'{scope} has no version {version}' if version is not None else f'{scope} has no history')
    return row['kind'], _decode(row['kind'], gzip.decompress(row['payload']))


def find_stat(scope: str, key: str):
    """The newest value of `stats[key]` recorded for a scope (e.g. the product source row a catalog belonged to)."""
    for item in versions(scope):
        if key in item['stats']:
            return item['stats'][key]
    return None


def scopes(prefix: str | None = None) -> list[dict]:
    """One row per dataset: latest version, number of versions, whether the latest is a deletion, pending held updates."""
    with _connect() as connection:
        rows = connection.execute(
            'SELECT d.scope, d.version, d.created_at, d.actor, d.reason, d.kind, d.raw_size, '
            '(SELECT COUNT(*) FROM data_versions c WHERE c.scope = d.scope) AS versions, '
            '(SELECT COUNT(*) FROM held_updates h WHERE h.scope = d.scope AND h.status = "pending") AS held '
            'FROM data_versions d WHERE d.version = (SELECT MAX(version) FROM data_versions m WHERE m.scope = d.scope) ORDER BY d.scope'
        ).fetchall()
    return [dict(row) for row in rows if not prefix or row['scope'].startswith(prefix)]


def pin(scope: str, version: int, pinned: bool = True) -> bool:
    with _connect() as connection:
        return connection.execute('UPDATE data_versions SET pinned = ? WHERE scope = ? AND version = ?', (1 if pinned else 0, scope, version)).rowcount > 0


def _prune(connection: sqlite3.Connection, scope: str) -> int:
    rows = connection.execute('SELECT version, created_at, pinned, raw_size FROM data_versions WHERE scope = ? ORDER BY version DESC', (scope,)).fetchall()
    if not rows:
        return 0
    big = max(row['raw_size'] for row in rows[:3]) > BIG_PAYLOAD_BYTES
    keep_last, keep_months = (KEEP_LAST_BIG, KEEP_MONTHS_BIG) if big else (KEEP_LAST, KEEP_MONTHS)
    keep = {row['version'] for row in rows[:keep_last]} | {row['version'] for row in rows if row['pinned']}
    seen_months: list[str] = []
    for row in rows:  # newest first: the first row met for a month is that month's newest
        month = row['created_at'][:7]
        if month not in seen_months:
            seen_months.append(month)
            if len(seen_months) <= keep_months:
                keep.add(row['version'])
    drop = [row['version'] for row in rows if row['version'] not in keep]
    for version in drop:
        connection.execute('DELETE FROM data_versions WHERE scope = ? AND version = ?', (scope, version))
    return len(drop)


def prune(scope: str | None = None) -> int:
    with _connect() as connection:
        targets = [scope] if scope else [row['scope'] for row in connection.execute('SELECT DISTINCT scope FROM data_versions')]
        return sum(_prune(connection, target) for target in targets)


# ------------------------------------------------------------------ held updates

def hold(scope: str, kind: str, data, *, findings: list[str], reason: str, actor: str | None = None, stats: dict | None = None, meta: dict | None = None) -> int:
    """Parks a refresh that looked worse than the stored data. An older pending hold of the same scope is superseded."""
    with _connect() as connection:
        connection.execute('UPDATE held_updates SET status = "superseded", resolved_at = ? WHERE scope = ? AND status = "pending"', (_now(), scope))
        cursor = connection.execute(
            'INSERT INTO held_updates (scope, created_at, actor, reason, findings, stats, meta, payload) VALUES (?,?,?,?,?,?,?,?)',
            (scope, _now(), actor or current_actor(), reason, json.dumps(findings), json.dumps(stats or {}), json.dumps({**(meta or {}), 'kind': kind}), gzip.compress(_encode(kind, data), 6)),
        )
        return cursor.lastrowid


def supersede_pending(scope: str) -> None:
    """A good refresh has just been saved: a hold for the same dataset is obsolete."""
    with _connect() as connection:
        connection.execute('UPDATE held_updates SET status = "superseded", resolved_at = ? WHERE scope = ? AND status = "pending"', (_now(), scope))


def _held_summary(row: sqlite3.Row) -> dict:
    return {'id': row['id'], 'scope': row['scope'], 'created_at': row['created_at'], 'actor': row['actor'], 'reason': row['reason'], 'findings': json.loads(row['findings']),
            'stats': json.loads(row['stats'] or '{}'), 'status': row['status'], 'resolved_at': row['resolved_at'], 'resolved_by': row['resolved_by']}


def held_updates(status: str | None = 'pending') -> list[dict]:
    with _connect() as connection:
        rows = connection.execute('SELECT * FROM held_updates' + (' WHERE status = ?' if status else '') + ' ORDER BY id DESC', (status,) if status else ()).fetchall()
    return [_held_summary(row) for row in rows]


def get_held(held_id: int) -> dict:
    """The held update with its data and meta. KeyError if unknown."""
    with _connect() as connection:
        row = connection.execute('SELECT * FROM held_updates WHERE id = ?', (held_id,)).fetchone()
    if row is None:
        raise KeyError(held_id)
    meta = json.loads(row['meta'] or '{}')
    return {**_held_summary(row), 'meta': meta, 'data': _decode(meta.get('kind', 'json'), gzip.decompress(row['payload']))}


def resolve_held(held_id: int, status: str, by: str | None = None, allow_from: tuple = ('pending',)) -> None:
    marks = ','.join('?' for _ in allow_from)
    with _connect() as connection:
        connection.execute(f'UPDATE held_updates SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ? AND status IN ({marks})',
                           (status, _now(), by or current_actor(), held_id, *allow_from))
