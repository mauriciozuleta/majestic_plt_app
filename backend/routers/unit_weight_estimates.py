"""Cached, one-time Haiku (no web search, no tools) estimate of a
count-based product's typical total pack weight — Market Opportunities'
count-vs-weight conversion (see countWeightConversion.js /
market_opportunities.py's own conversion_note field). Synchronous, unlike
weight_research.py's background-job pattern: a Haiku call with no tools is
fast (no multi-search research to wait on), so there's no "looks like a
dead job" risk from tying it to the request/response cycle.

Cache-first, same discipline as weight_research.py: every signature already
in models.ProductUnitWeightEstimate is served straight from the table, no
API call; only a genuine cache miss reaches Haiku. `dry_run` lets a caller
find out how many of a batch of signatures would be genuine (uncached)
misses WITHOUT spending anything — used to report the real pre-spend count
before a bulk estimate run, per this feature's own cost-guardrail
requirement."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..unit_weight_estimates.claude_client import MAX_ITEMS_PER_BATCH, estimate_unit_weights

router = APIRouter()


class UnitWeightItem(BaseModel):
    signature: str
    description: str


class UnitWeightRequest(BaseModel):
    items: list[UnitWeightItem]
    dry_run: bool = False


def _serialize(row: models.ProductUnitWeightEstimate) -> dict:
    return {'weight_grams': row.weight_grams, 'note': row.note, 'estimated_at': row.estimated_at, 'cached': True}


@router.get('/api/unit-weight-estimates')
def list_unit_weight_estimates(db: Session = Depends(get_db)):
    rows = db.query(models.ProductUnitWeightEstimate).all()
    return {'results': {row.signature: _serialize(row) for row in rows}}


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


@router.post('/api/unit-weight-estimates')
def request_unit_weight_estimates(request: UnitWeightRequest, db: Session = Depends(get_db)):
    if not request.items:
        return {'results': {}, 'cache_hit_count': 0, 'cache_miss_count': 0}

    by_signature = {item.signature: item for item in request.items}
    existing = (
        db.query(models.ProductUnitWeightEstimate)
        .filter(models.ProductUnitWeightEstimate.signature.in_(by_signature.keys()))
        .all()
    )
    results = {row.signature: _serialize(row) for row in existing}
    miss_signatures = [sig for sig in by_signature if sig not in results]

    if request.dry_run:
        # No Haiku call, no writes — just report what WOULD need to be spent.
        return {
            'results': results,
            'cache_hit_count': len(results),
            'cache_miss_count': len(miss_signatures),
            'miss_signatures': miss_signatures,
        }

    if miss_signatures:
        now = datetime.now(timezone.utc).isoformat()
        for chunk in _chunks(miss_signatures, MAX_ITEMS_PER_BATCH):
            chunk_items = [{'signature': sig, 'description': by_signature[sig].description} for sig in chunk]
            estimated = estimate_unit_weights(chunk_items)
            for result in estimated:
                signature = result['signature']
                # Committed one row at a time (not batched with the rest of
                # the chunk) so a UNIQUE-constraint race — two overlapping
                # requests both seeing this signature as a genuine miss and
                # both estimating it (e.g. a double-invoked effect on the
                # frontend) — only ever costs a wasted Haiku call, never a
                # 500: the loser's insert is caught and it falls back to
                # whatever the winner already persisted, same as a real
                # cache hit.
                try:
                    db.add(
                        models.ProductUnitWeightEstimate(
                            signature=signature,
                            description=by_signature[signature].description,
                            weight_grams=result['weight_grams'],
                            note=result['note'],
                            estimated_at=now,
                        )
                    )
                    db.commit()
                    results[signature] = {'weight_grams': result['weight_grams'], 'note': result['note'], 'estimated_at': now, 'cached': False}
                except IntegrityError:
                    db.rollback()
                    winner = db.query(models.ProductUnitWeightEstimate).filter_by(signature=signature).first()
                    if winner:
                        results[signature] = _serialize(winner)

    return {
        'results': results,
        'cache_hit_count': len(existing),
        'cache_miss_count': len(miss_signatures),
    }
