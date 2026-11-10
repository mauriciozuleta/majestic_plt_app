"""Shared persistence for "last successfully fetched" market-data snapshots
(Colombia price comparison, USA sourcing) — one row per source key, storing
its most recent fetch result + timestamp, so a page load can show the last
real fetch without forcing a new one. The fetch pipeline itself only ever
runs from an Update click; this just keeps its last result from vanishing
on refresh.

Every product dataset (data_history.is_versioned_snapshot) also gets its new state appended to the data history BEFORE the live row is written, so a
refresh can be undone and a failed history write refuses the update. A refresh made with `guard=True` that looks worse than what is stored (empty, far
fewer products) is parked for a person's approval instead (HeldForApproval); `force=True` skips that check."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import data_history, models
from .data_history import HeldForApproval


def _stored_products(db: Session, source: str):
    row = db.query(models.PriceComparisonSnapshot).filter_by(source=source).first()
    if not row:
        return None
    try:
        return json.loads(row.data_json)
    except ValueError:
        return None


def save_snapshot(db: Session, source: str, products: list, *, guard: bool = False, force: bool = False, reason: str = 'refresh', meta: dict | None = None):
    versioned = data_history.is_versioned_snapshot(source)
    scope = data_history.snapshot_scope(source)
    if versioned and guard and not force:
        findings = data_history.guard.check_products(_stored_products(db, source), products)
        if findings:
            held_id = data_history.store.hold(scope, 'json', products, findings=findings, reason=reason, meta=meta,
                                              stats={'diff': data_history.diff.diff_products(_stored_products(db, source), products)})
            raise HeldForApproval(scope, held_id, findings)
    # A product catalog is normalized (price per kg, pack weight, items per pack) the moment it is stored — see catalog_normalization/catalog.py. Only
    # the deterministic part and the already-researched weights run here; nothing is fetched from the web.
    from .catalog_normalization.catalog import annotate_with_db, is_catalog_source

    if is_catalog_source(source) and isinstance(products, list):
        annotate_with_db(db, source, products)
    if versioned:
        stats = {'products': len(products) if isinstance(products, list) else None}
        if meta and meta.get('source'):
            stats['source'] = meta['source']
        data_history.store.record(scope, 'json', products, reason=reason, stats=stats)
        data_history.store.supersede_pending(scope)
    fetched_at = datetime.now(timezone.utc).isoformat()
    snapshot = db.query(models.PriceComparisonSnapshot).filter_by(source=source).first()
    if snapshot:
        snapshot.data_json = json.dumps(products)
        snapshot.fetched_at = fetched_at
    else:
        db.add(models.PriceComparisonSnapshot(source=source, data_json=json.dumps(products), fetched_at=fetched_at))
    db.commit()


def record_current(db: Session, source: str, reason: str, meta: dict | None = None) -> None:
    """For code that rewrites a snapshot's `data_json` directly (deleting products, re-annotating): appends what is stored now to the history."""
    if not data_history.is_versioned_snapshot(source):
        return
    products = _stored_products(db, source)
    if products is None:
        return
    stats = {'products': len(products) if isinstance(products, list) else None}
    if meta and meta.get('source'):
        stats['source'] = meta['source']
    data_history.store.record(data_history.snapshot_scope(source), 'json', products, reason=reason, stats=stats)


def list_snapshots(db: Session, sources: list[str]):
    rows = db.query(models.PriceComparisonSnapshot).filter(models.PriceComparisonSnapshot.source.in_(sources)).all()
    return [{'source': row.source, 'products': json.loads(row.data_json), 'fetched_at': row.fetched_at} for row in rows]
