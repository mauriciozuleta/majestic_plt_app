"""Cached Claude product matching for Market Opportunities' AI match
tier (see backend/product_matching/claude_client.py). Cache-first: a source
product already judged against the same target country and the same
candidate list is served from models.ProductMatchCache with no API call."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..product_matching.claude_client import MAX_SOURCES_PER_BATCH, PROMPT_VERSION, judge_matches

router = APIRouter()


class MatchSource(BaseModel):
    key: str
    description: str


class MatchGroup(BaseModel):
    candidates: list[str]
    sources: list[MatchSource]


class MatchRequest(BaseModel):
    target_country: str
    groups: list[MatchGroup]


def _signature(target_country: str, key: str, candidates: list[str]) -> str:
    candidate_hash = hashlib.sha1('\n'.join(sorted(candidates)).encode('utf-8')).hexdigest()
    return hashlib.sha1(f'{PROMPT_VERSION}|{target_country.lower()}|{key.lower()}|{candidate_hash}'.encode('utf-8')).hexdigest()


def _serialize(row: models.ProductMatchCache, cached: bool) -> dict:
    return {'matches': json.loads(row.matches_json), 'note': row.note, 'cached': cached}


@router.post('/api/product-matches')
def request_product_matches(request: MatchRequest, db: Session = Depends(get_db)):
    """Returns {"results": {key: {"matches": [...], "note", "cached"}},
    "errors", "cache_hit_count", "cache_miss_count"}. A source missing from
    `results` belongs to a batch whose AI call failed (reported in `errors`)."""
    results: dict[str, dict] = {}
    errors: list[str] = []
    hits = misses = 0
    for group in request.groups:
        candidates = sorted({name.strip() for name in group.candidates if name.strip()})
        if not candidates:
            continue
        pending = []
        for source in group.sources:
            signature = _signature(request.target_country, source.key, candidates)
            row = db.query(models.ProductMatchCache).filter_by(signature=signature).first()
            if row:
                results[source.key] = _serialize(row, cached=True)
                hits += 1
            else:
                pending.append((source, signature))
        misses += len(pending)

        for start in range(0, len(pending), MAX_SOURCES_PER_BATCH):
            chunk = pending[start : start + MAX_SOURCES_PER_BATCH]
            try:
                judged = judge_matches([source.description for source, _ in chunk], candidates, request.target_country)
            except Exception as exc:
                # One failed batch never sinks the rest: its products are left
                # out of `results` (and uncached, so they're retried next run).
                errors.append(str(exc))
                continue
            now = datetime.now(timezone.utc).isoformat()
            for (source, signature), result in zip(chunk, judged):
                row = models.ProductMatchCache(
                    signature=signature,
                    source_name=source.key,
                    target_country=request.target_country,
                    matches_json=json.dumps(result['matches']),
                    note=result['note'],
                    created_at=now,
                )
                try:
                    db.add(row)
                    db.commit()
                except IntegrityError:
                    # A concurrent request already judged this exact item.
                    db.rollback()
                    row = db.query(models.ProductMatchCache).filter_by(signature=signature).first()
                results[source.key] = _serialize(row, cached=False)

    return {'results': results, 'errors': errors, 'cache_hit_count': hits, 'cache_miss_count': misses}
