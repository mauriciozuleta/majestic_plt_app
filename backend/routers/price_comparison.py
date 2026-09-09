"""
Two independent endpoints (not one combined one) — the frontend calls both
separately so one source failing never blocks the other's data from
showing (see ColombiaProductAnalysisView's Update handler).

Each successful fetch is persisted as a snapshot (last-known-good products +
timestamp) so /snapshot can hand back the last real fetch on page load —
the pipeline itself still only ever runs from the Update button, this just
keeps its last result from vanishing on refresh.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..price_sources.corabastos import fetch_corabastos_products
from ..price_sources.la_mayorista import fetch_la_mayorista_products
from ..price_sources.text_normalize import normalize_id
from ..snapshot_store import list_snapshots, save_snapshot

router = APIRouter()

_SNAPSHOT_SOURCES = ['la_mayorista', 'corabastos']


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
