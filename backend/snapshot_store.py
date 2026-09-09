"""Shared persistence for "last successfully fetched" market-data snapshots
(Colombia price comparison, USA sourcing) — one row per source key, storing
its most recent fetch result + timestamp, so a page load can show the last
real fetch without forcing a new one. The fetch pipeline itself only ever
runs from an Update click; this just keeps its last result from vanishing
on refresh."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models


def save_snapshot(db: Session, source: str, products: list):
    fetched_at = datetime.now(timezone.utc).isoformat()
    snapshot = db.query(models.PriceComparisonSnapshot).filter_by(source=source).first()
    if snapshot:
        snapshot.data_json = json.dumps(products)
        snapshot.fetched_at = fetched_at
    else:
        db.add(models.PriceComparisonSnapshot(source=source, data_json=json.dumps(products), fetched_at=fetched_at))
    db.commit()


def list_snapshots(db: Session, sources: list[str]):
    rows = db.query(models.PriceComparisonSnapshot).filter(models.PriceComparisonSnapshot.source.in_(sources)).all()
    return [{'source': row.source, 'products': json.loads(row.data_json), 'fetched_at': row.fetched_at} for row in rows]
