"""User-entered corrections for one exact priced row's price and/or pack
weight — the manual escape hatch for when the official conversion is
missing and AI research (see weight_research.py) is wrong, stale, or
hasn't been run. Plain synchronous CRUD, no background job: unlike weight
research, this never calls an external API. Global, not per-company — see
models.ProductCustomOverride."""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from .. import models
from ..database import SessionLocal

router = APIRouter()


class CustomOverrideIn(BaseModel):
    # signature lives in the body, not the URL path — these signatures
    # routinely contain "/" (e.g. a USA unit like "USD/lb"), which even
    # percent-encoded (%2F) doesn't reliably survive as a single path
    # segment through uvicorn/Starlette's routing.
    signature: str
    custom_price: float | None = None
    custom_weight_kg: float | None = None


class ClearOverrideIn(BaseModel):
    signature: str


@router.get('/product-custom-overrides')
def list_custom_overrides():
    db = SessionLocal()
    try:
        rows = db.query(models.ProductCustomOverride).all()
        return {
            row.signature: {
                'custom_price': row.custom_price,
                'custom_weight_kg': row.custom_weight_kg,
                'updated_at': row.updated_at,
            }
            for row in rows
        }
    finally:
        db.close()


@router.post('/product-custom-overrides')
def set_custom_override(body: CustomOverrideIn):
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).isoformat()
        existing = db.query(models.ProductCustomOverride).filter_by(signature=body.signature).first()
        if existing:
            existing.custom_price = body.custom_price
            existing.custom_weight_kg = body.custom_weight_kg
            existing.updated_at = now
        else:
            db.add(
                models.ProductCustomOverride(
                    signature=body.signature,
                    custom_price=body.custom_price,
                    custom_weight_kg=body.custom_weight_kg,
                    updated_at=now,
                )
            )
        db.commit()
        return {
            'signature': body.signature,
            'custom_price': body.custom_price,
            'custom_weight_kg': body.custom_weight_kg,
            'updated_at': now,
        }
    finally:
        db.close()


@router.post('/product-custom-overrides/clear')
def clear_custom_override(body: ClearOverrideIn):
    db = SessionLocal()
    try:
        db.query(models.ProductCustomOverride).filter_by(signature=body.signature).delete()
        db.commit()
        return {'status': 'cleared'}
    finally:
        db.close()
