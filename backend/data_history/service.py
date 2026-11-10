"""Everything that needs the app's models: the start-up baseline, restoring a version, approving or rejecting a held update, recording a file.
Kept apart from store.py (pure storage) so importing the history never drags the models in."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .. import market_size_store, models, snapshot_store
from . import diff as diffs
from . import is_versioned_snapshot, market_size_scope, snapshot_scope, store

log = logging.getLogger('data_history')
BACKEND = Path(__file__).resolve().parents[1]
FILE_DIRS = (BACKEND / 'country_profiles', BACKEND / 'competitiveness_analyses')


# ------------------------------------------------------------------ files

def file_scope(path: Path) -> str:
    return 'file:' + Path(path).resolve().relative_to(BACKEND).as_posix()


def record_file(path: Path, reason: str) -> dict | None:
    """Appends a file's current content to the history. Called after a refresh/build wrote it; never raises into the caller (the file is already written)."""
    try:
        path = Path(path)
        if not path.is_file():
            return None
        return store.record(file_scope(path), 'file', path.read_bytes(), reason=reason, stats={'size': path.stat().st_size})
    except Exception:  # noqa: BLE001 — the work this records has already happened
        log.exception('could not record %s in the data history', path)
        return None


def tracked_files() -> list[Path]:
    """Generated files with a history: country profiles, competitiveness analyses, every tax calculator's tariff file."""
    found: list[Path] = []
    for folder in FILE_DIRS:
        if folder.exists():
            found.extend(sorted(item for item in folder.rglob('*') if item.is_file() and not item.name.startswith('.') and item.suffix == '.md'))
    from ..tax_calc import CALCULATORS

    for calculator in CALCULATORS.values():
        try:
            path = calculator.path
        except Exception:  # noqa: BLE001 — a calculator without a data file (Sint Maarten)
            continue
        if path and Path(path).is_file():
            found.append(Path(path))
    return found


# ------------------------------------------------------------------ baseline

def baseline(db: Session) -> dict:
    """Records the current state of every dataset. The first time it is the baseline; later (each start-up) it only adds a version for a dataset whose
    content differs from its latest version, i.e. something changed outside the hooked write paths."""
    added, unchanged = [], 0

    def put(scope: str, kind: str, data, stats: dict) -> None:
        nonlocal unchanged
        first = store.latest(scope) is None
        done = store.record(scope, kind, data, reason='baseline' if first else 'changed outside the history hooks (found at start-up)', actor='baseline', stats=stats)
        if done:
            added.append(scope)
        else:
            unchanged += 1

    custom = {f'custom_{row.id}': row for row in db.query(models.ProductSource).all()}
    for row in db.query(models.PriceComparisonSnapshot).all():
        if not is_versioned_snapshot(row.source):
            continue
        try:
            products = json.loads(row.data_json)
        except ValueError:
            continue
        stats = {'products': len(products) if isinstance(products, list) else None}
        if row.source in custom:
            stats['source'] = _source_meta(custom[row.source])
        put(snapshot_scope(row.source), 'json', products, stats)
    for row in db.query(models.MarketSizeSnapshot).all():
        put(market_size_scope(row.kind), 'json', {'flow': row.flow, 'chapters': json.loads(row.chapters_json), 'data': json.loads(row.data_json)}, {})
    from ..catalog_normalization import hs_store

    assignments = hs_store.export_assignments(db)
    if assignments:
        put(hs_store.HISTORY_SCOPE, 'json', assignments, {'assignments': len(assignments)})
    for path in tracked_files():
        put(file_scope(path), 'file', path.read_bytes(), {'size': path.stat().st_size})
    return {'added': added, 'unchanged': unchanged}


def _source_meta(row: models.ProductSource) -> dict:
    return {'id': row.id, 'country_name': row.country_name, 'name': row.name, 'url': row.url, 'currency': row.currency, 'analysis_type': row.analysis_type,
            'status': row.status, 'status_message': row.status_message, 'origin': row.origin, 'product_count': row.product_count, 'last_loaded_at': row.last_loaded_at}


# ------------------------------------------------------------------ restore

def _decoded(scope: str, version: int | None):
    try:
        return store.load(scope, version)
    except KeyError as error:
        raise LookupError(str(error)) from error


def restore(db: Session, scope: str, version: int, actor: str = 'user') -> dict:
    """Puts an old version back as the live data. It becomes a NEW version (history is never rewritten). Raises LookupError / ValueError with a message."""
    kind, data = _decoded(scope, version)
    if kind == 'deleted':
        raise ValueError('That version is the marker of a deletion — pick an earlier version to bring the data back.')
    reason = f'restored version {version}'
    with store.acting_as(actor):
        if scope.startswith('snapshot:'):
            source = scope.split(':', 1)[1]
            row = None
            if source.startswith('custom_'):
                row = db.get(models.ProductSource, source[len('custom_'):])
                if row is None:  # the source was deleted: rebuild its row from what the history remembers of it
                    meta = store.find_stat(scope, 'source')
                    if not meta:
                        raise ValueError('The source was deleted and the history does not remember its settings, so it cannot be recreated.')
                    row = models.ProductSource(id=meta['id'], country_name=meta['country_name'], name=meta['name'], url=meta.get('url'), currency=meta.get('currency'),
                                               analysis_type=meta.get('analysis_type') or 'wholesaler', origin=meta.get('origin'), status='ok', product_count=0,
                                               created_at=datetime.now(timezone.utc).isoformat())
                    db.add(row)
            snapshot_store.save_snapshot(db, source, data, force=True, reason=reason)
            if row is not None:
                row.product_count, row.status = len(data), 'ok'
                row.status_message, row.last_loaded_at = f'Restored from data history version {version}.', datetime.now(timezone.utc).isoformat()
            db.commit()
            return {'scope': scope, 'restored_version': version, 'products': len(data)}
        if scope.startswith('market_size:'):
            market_size_store.save_snapshot(db, scope.split(':', 1)[1], data['flow'], data['chapters'], data['data'], force=True, reason=reason, computed_at=data['data'].get('computed_at'))
            return {'scope': scope, 'restored_version': version}
        if scope == 'hs:assignments':
            from ..catalog_normalization import hs_store

            hs_store.replace_assignments(db, data)
            hs_store.record_history(db, reason)
            hs_store.reannotate_catalogs(db, reason)
            return {'scope': scope, 'restored_version': version, 'assignments': len(data)}
        if scope.startswith('file:'):
            path = (BACKEND / scope[len('file:'):]).resolve()
            if BACKEND not in path.parents:
                raise ValueError('That path is outside the app.')
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + '.restore.tmp')
            temp.write_bytes(data)
            os.replace(temp, path)
            store.record(scope, 'file', data, reason=reason, stats={'size': len(data)})
            _reload_calculators(path)
            return {'scope': scope, 'restored_version': version, 'bytes': len(data)}
    raise ValueError(f'Unknown kind of dataset: {scope}')


def _reload_calculators(path: Path) -> None:
    from ..tax_calc import CALCULATORS

    for calculator in CALCULATORS.values():
        try:
            if Path(calculator.path).resolve() == path and hasattr(calculator, '_load'):
                calculator._load()
        except Exception:  # noqa: BLE001
            log.exception('could not reload %s after a restore', path)


# ------------------------------------------------------------------ held updates

def compare_with_live(db: Session, held_id: int) -> dict:
    """What approving a held update would change: the live data against the held data."""
    held = store.get_held(held_id)
    scope = held['scope']
    if scope.startswith('market_size:'):
        kind = scope.split(':', 1)[1]
        live = market_size_store.get_snapshot(db, kind)
        return diffs.diff_market_size(kind, live['data'] if live else None, held['data']['data'])
    source = scope.split(':', 1)[1]
    live = snapshot_store.list_snapshots(db, [source])
    return diffs.diff_products(live[0]['products'] if live else None, held['data'])


def approve(db: Session, held_id: int, by: str = 'user') -> dict:
    held = store.get_held(held_id)
    if held['status'] != 'pending':
        raise ValueError(f'This update is already {held["status"]}.')
    scope, reason = held['scope'], f'approved: {held["reason"]}'[:200]
    with store.acting_as(by):
        if scope.startswith('market_size:'):
            kind, data = scope.split(':', 1)[1], held['data']
            market_size_store.save_snapshot(db, kind, data['flow'], data['chapters'], data['data'], force=True, reason=reason, computed_at=held['created_at'])
        else:
            source, products = scope.split(':', 1)[1], held['data']
            if source.startswith('custom_'):
                from ..routers import product_sources  # late import: the router imports this package

                row = db.get(models.ProductSource, source[len('custom_'):])
                if row is None:
                    raise ValueError('The source this update belongs to no longer exists.')
                product_sources._store(db, row, products, held['meta'].get('origin') or 'site', held['meta'].get('note') or reason, force=True)
                db.commit()
            else:
                snapshot_store.save_snapshot(db, source, products, force=True, reason=reason)
    store.resolve_held(held_id, 'approved', by, allow_from=('pending', 'superseded'))
    return {'id': held_id, 'status': 'approved', 'scope': scope}


def reject(held_id: int, by: str = 'user') -> dict:
    held = store.get_held(held_id)
    if held['status'] != 'pending':
        raise ValueError(f'This update is already {held["status"]}.')
    store.resolve_held(held_id, 'rejected', by)
    return {'id': held_id, 'status': 'rejected', 'scope': held['scope']}


# ------------------------------------------------------------------ labels for the screens

def scope_label(db: Session, scope: str) -> str:
    from ..routers.product_sources import BUILT_IN_SOURCES

    if scope.startswith('snapshot:'):
        source = scope.split(':', 1)[1]
        for country, name, _url, keys in BUILT_IN_SOURCES:
            if source in keys:
                return f'{country} · {name}'
        if source.startswith('custom_'):
            row = db.get(models.ProductSource, source[len('custom_'):])
            meta = store.find_stat(scope, 'source') or {}
            if row:
                return f'{row.country_name} · {row.name}'
            if meta:
                return f'{meta.get("country_name")} · {meta.get("name")} (deleted)'
        return {'la_mayorista': 'Colombia · La Mayorista', 'corabastos': 'Colombia · Corabastos'}.get(source, source)
    if scope == 'hs:assignments':
        return 'HS codes · assignments (all countries)'
    if scope.startswith('market_size:'):
        return f'Market size · {scope.split(":", 1)[1].upper()}'
    if scope.startswith('file:'):
        return 'File · ' + scope[len('file:'):]
    return scope
