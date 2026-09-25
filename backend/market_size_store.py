"""Persistence for SAM/TAM Overview's computed AGGREGATE (region/category
totals + per-country breakdown) — deliberately separate from
snapshot_store.py, which caches the underlying per-country/global Comtrade
ROWS those aggregates are built from. The aggregation itself (resolving
qualifying chapters against Comtrade, walking each country's own year,
summing per region/category) is real work even when every underlying row is
a cache hit, and neither sam_overview nor tam_global_overview persisted its
own output before this module existed — every tab view recomputed it live.
See models.MarketSizeSnapshot and MARKET_SIZING_METHODOLOGY.md."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models


def get_snapshot(db: Session, kind: str) -> dict | None:
    """None if this kind (`'sam'` | `'tam'`) has never been computed yet —
    the caller computes live and calls save_snapshot itself in that case
    (see sam_overview / tam_global_overview)."""
    row = db.query(models.MarketSizeSnapshot).filter_by(kind=kind).first()
    if not row:
        return None
    return {
        'data': json.loads(row.data_json),
        'chapters': json.loads(row.chapters_json),
        'flow': row.flow,
        'computed_at': row.computed_at,
    }


def save_snapshot(db: Session, kind: str, flow: str, chapters: list[str], data: dict) -> dict:
    """Overwrites (or creates) this kind's one stored row. `data` is the
    already-computed response body (regions/categories/etc, no computed_at
    of its own yet) — `computed_at` is stamped here and folded into the
    stored (and returned) data dict, so every caller — the first-ever
    compute, a manual recompute, or the chatbox tool — gets back exactly
    what a normal GET would now return, computed_at included."""
    computed_at = datetime.now(timezone.utc).isoformat()
    stamped = {**data, 'computed_at': computed_at}
    row = db.query(models.MarketSizeSnapshot).filter_by(kind=kind).first()
    if row:
        row.flow = flow
        row.chapters_json = json.dumps(chapters)
        row.data_json = json.dumps(stamped)
        row.computed_at = computed_at
    else:
        db.add(
            models.MarketSizeSnapshot(
                kind=kind,
                flow=flow,
                chapters_json=json.dumps(chapters),
                data_json=json.dumps(stamped),
                computed_at=computed_at,
            )
        )
    db.commit()
    return stamped
