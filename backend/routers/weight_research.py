"""Researches the standard net weight (in kg) of wholesale packs/units that
the price scrapers can't convert to $/kg on their own — a USA produce
carton whose weight isn't in the scraped report text, or a Colombia
count-based package (e.g. "CAJA (10 per package)") with no stated weight.
Global (not per-company): a carton's standard weight is a fact about the
pack, reusable across every company that looks at the same source data —
see models.ProductWeightResearch.

Same "runs as a real background task, tracked via a sibling marker file"
pattern as country_profile/competitiveness (see background_jobs.py) — one
research call can take a while (multiple searches across up to 25 items),
and tying it to the request/response cycle would look like a dead job the
moment the frontend navigates away."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from .. import models
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..database import SessionLocal
from ..weight_research.claude_client import MAX_ITEMS_PER_BATCH, research_pack_weights

router = APIRouter()

JOB_MARKER_PATH = Path(__file__).resolve().parent.parent / 'weight_research_data' / '_job.marker'


class WeightResearchItem(BaseModel):
    signature: str
    description: str


class WeightResearchRequest(BaseModel):
    items: list[WeightResearchItem]


@router.get('/weight-research')
def list_weight_research():
    db = SessionLocal()
    try:
        rows = db.query(models.ProductWeightResearch).all()
        results = {
            row.signature: {
                'weight_kg': row.weight_kg,
                'confidence': row.confidence,
                'note': row.note,
                'sources': json.loads(row.sources_json),
                'researched_at': row.researched_at,
            }
            for row in rows
        }
    finally:
        db.close()
    return {
        'building': is_building(JOB_MARKER_PATH),
        'error': get_error(JOB_MARKER_PATH),
        'results': results,
    }


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _run_weight_research(items):
    try:
        by_signature = {item['signature']: item for item in items}
        all_results = []
        for chunk in _chunks(items, MAX_ITEMS_PER_BATCH):
            all_results.extend(research_pack_weights(chunk))

        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc).isoformat()
            for result in all_results:
                signature = result['signature']
                description = by_signature[signature]['description']
                sources_json = json.dumps(result['sources'])
                existing = db.query(models.ProductWeightResearch).filter_by(signature=signature).first()
                if existing:
                    existing.description = description
                    existing.weight_kg = result['weight_kg']
                    existing.confidence = result['confidence']
                    existing.note = result['note']
                    existing.sources_json = sources_json
                    existing.researched_at = now
                else:
                    db.add(
                        models.ProductWeightResearch(
                            signature=signature,
                            description=description,
                            weight_kg=result['weight_kg'],
                            confidence=result['confidence'],
                            note=result['note'],
                            sources_json=sources_json,
                            researched_at=now,
                        )
                    )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        mark_error(JOB_MARKER_PATH, str(exc))
    finally:
        clear_building(JOB_MARKER_PATH)


@router.post('/weight-research')
def start_weight_research(request: WeightResearchRequest, background_tasks: BackgroundTasks):
    if is_building(JOB_MARKER_PATH):
        return {'status': 'already_building'}
    if not request.items:
        return {'status': 'no_items'}

    mark_building(JOB_MARKER_PATH)
    items = [item.model_dump() for item in request.items]
    background_tasks.add_task(_run_weight_research, items)
    return {'status': 'started', 'item_count': len(items)}
