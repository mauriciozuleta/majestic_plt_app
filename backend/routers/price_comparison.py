"""
Two independent endpoints (not one combined one) — the frontend calls both
separately so one source failing never blocks the other's data from
showing (see ColombiaProductAnalysisView's Update handler).

Each successful fetch is persisted as a snapshot (last-known-good products +
timestamp) so /snapshot can hand back the last real fetch on page load —
the pipeline itself still only ever runs from the Update button, this just
keeps its last result from vanishing on refresh.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..database import SessionLocal, get_db
from ..price_sources.corabastos import fetch_corabastos_products
from ..price_sources.la_mayorista import fetch_la_mayorista_products
from ..price_sources.text_normalize import normalize_id
from ..snapshot_store import list_snapshots, save_snapshot
from ..translation.resolve import resolve_many

router = APIRouter()

_SNAPSHOT_SOURCES = ['la_mayorista', 'corabastos']

# Same "background task + sibling marker file" pattern as weight_research.py
# — resolving a batch of names through Tier 3 (local model) / Tier 4 (web
# search) can take a while, and tying it to the request/response cycle
# would look like a dead job the moment the frontend navigates away.
_TRANSLATION_JOB_MARKER_PATH = Path(__file__).resolve().parent.parent / 'translation_suggestions_data' / '_job.marker'


class TranslationSuggestionItem(BaseModel):
    product_key: str
    name_es: str


class TranslationSuggestionRequest(BaseModel):
    items: list[TranslationSuggestionItem]


@router.get('/market-analysis/colombia/la-mayorista')
def get_la_mayorista_prices(db: Session = Depends(get_db)):
    try:
        products = fetch_la_mayorista_products()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'La Mayorista fetch failed: {exc}') from exc
    save_snapshot(db, 'la_mayorista', products)
    return products


@router.get('/market-analysis/colombia/corabastos')
def get_corabastos_prices(db: Session = Depends(get_db)):
    try:
        products = fetch_corabastos_products()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Corabastos fetch failed: {exc}') from exc
    save_snapshot(db, 'corabastos', products)
    return products


@router.get('/market-analysis/colombia/snapshot', response_model=list[schemas.PriceComparisonSnapshotOut])
def get_price_comparison_snapshot(db: Session = Depends(get_db)):
    return list_snapshots(db, _SNAPSHOT_SOURCES)


@router.get('/market-analysis/colombia/translations', response_model=list[schemas.ProductTranslationOverrideOut])
def list_translation_overrides(db: Session = Depends(get_db)):
    return db.query(models.ProductTranslationOverride).all()


@router.put('/market-analysis/colombia/translations', response_model=schemas.ProductTranslationOverrideOut)
def upsert_translation_override(payload: schemas.ProductTranslationOverrideIn, db: Session = Depends(get_db)):
    key = normalize_id(payload.product_key)
    translation_en = payload.translation_en.strip()
    if not translation_en:
        raise HTTPException(status_code=400, detail='translation_en must not be empty')

    override = db.query(models.ProductTranslationOverride).filter_by(product_key=key).first()
    if override:
        override.translation_en = translation_en
    else:
        override = models.ProductTranslationOverride(product_key=key, translation_en=translation_en)
        db.add(override)
    db.commit()
    db.refresh(override)
    return override


@router.get('/market-analysis/colombia/translation-suggestions')
def list_translation_suggestions(db: Session = Depends(get_db)):
    rows = db.query(models.ProductTranslationSuggestion).all()
    return {
        'building': is_building(_TRANSLATION_JOB_MARKER_PATH),
        'error': get_error(_TRANSLATION_JOB_MARKER_PATH),
        'results': [
            {
                'product_key': row.product_key,
                'name_es': row.name_es,
                'suggestion_en': row.suggestion_en,
                'tier': row.tier,
                'confidence': row.confidence,
                'created_at': row.created_at,
            }
            for row in rows
        ],
    }


def _run_translation_suggestions(items: list[dict]) -> None:
    try:
        results = resolve_many([item['name_es'] for item in items])

        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                result = results.get(item['name_es'])
                if not result:
                    continue
                existing = db.query(models.ProductTranslationSuggestion).filter_by(product_key=item['product_key']).first()
                if existing:
                    existing.name_es = item['name_es']
                    existing.suggestion_en = result['suggestion_en']
                    existing.tier = result['tier']
                    existing.confidence = result['confidence']
                    existing.created_at = now
                else:
                    db.add(
                        models.ProductTranslationSuggestion(
                            product_key=item['product_key'],
                            name_es=item['name_es'],
                            suggestion_en=result['suggestion_en'],
                            tier=result['tier'],
                            confidence=result['confidence'],
                            created_at=now,
                        )
                    )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        mark_error(_TRANSLATION_JOB_MARKER_PATH, str(exc))
    finally:
        clear_building(_TRANSLATION_JOB_MARKER_PATH)


@router.post('/market-analysis/colombia/translation-suggestions')
def start_translation_suggestions(
    request: TranslationSuggestionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    if is_building(_TRANSLATION_JOB_MARKER_PATH):
        return {'status': 'already_building'}
    if not request.items:
        return {'status': 'no_items'}

    # A name already suggested (pending review) or already confirmed into
    # the permanent dictionary since the frontend last fetched its list
    # isn't re-resolved — Tier 3/4 only ever run once per product, ever.
    already_suggested = {row.product_key for row in db.query(models.ProductTranslationSuggestion.product_key).all()}
    already_confirmed = {row.product_key for row in db.query(models.ProductTranslationOverride.product_key).all()}
    items = [
        item.model_dump()
        for item in request.items
        if item.product_key not in already_suggested and item.product_key not in already_confirmed
    ]
    if not items:
        return {'status': 'no_items'}

    mark_building(_TRANSLATION_JOB_MARKER_PATH)
    background_tasks.add_task(_run_translation_suggestions, items)
    return {'status': 'started', 'item_count': len(items)}


@router.post('/market-analysis/colombia/translation-suggestions/{product_key}/confirm', response_model=schemas.ProductTranslationOverrideOut)
def confirm_translation_suggestion(product_key: str, db: Session = Depends(get_db)):
    """A human confirming a Tier 3/4 suggestion promotes it into the
    permanent dictionary (ProductTranslationOverride) — the same table a
    manually-typed translation is saved into above — so the same product
    name never needs Tier 3/4 resolution again."""
    suggestion = db.query(models.ProductTranslationSuggestion).filter_by(product_key=product_key).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail='No pending suggestion for this product')

    override = db.query(models.ProductTranslationOverride).filter_by(product_key=product_key).first()
    if override:
        override.translation_en = suggestion.suggestion_en
    else:
        override = models.ProductTranslationOverride(product_key=product_key, translation_en=suggestion.suggestion_en)
        db.add(override)
    db.delete(suggestion)
    db.commit()
    db.refresh(override)
    return override


@router.delete('/market-analysis/colombia/translation-suggestions/{product_key}')
def reject_translation_suggestion(product_key: str, db: Session = Depends(get_db)):
    db.query(models.ProductTranslationSuggestion).filter_by(product_key=product_key).delete()
    db.commit()
    return {'status': 'deleted'}
