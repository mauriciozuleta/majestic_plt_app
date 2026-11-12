"""HS codes of the catalog products (backend/catalog_normalization/hs.py, hs_store.py): status, the review queue, validation, suggestions (free sources first; Claude only
when asked) and saving. A suggestion is never saved by this API on its own: `save` is what a person (or an agent acting for one) calls."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..catalog_normalization import hs, hs_store
from ..database import get_db

router = APIRouter(prefix='/api/hs-codes', tags=['hs-codes'])

MAX_MODEL_ITEMS = 12  # per call to Claude


class ItemIn(BaseModel):
    country: str
    name: str
    category: str | None = None


class CheckIn(ItemIn):
    code: str


class SuggestIn(BaseModel):
    items: list[ItemIn]
    allow_peer: bool = True
    allow_ai: bool = False


class SaveItem(CheckIn):
    method: str | None = None
    confidence: str | None = None
    note: str | None = None
    status: str | None = None  # default: confirmed by a person; 'suggested' saves an unreviewed suggestion


class SaveIn(BaseModel):
    items: list[SaveItem]
    saved_by: str = 'user'


@router.get('/status')
def status(db: Session = Depends(get_db)):
    return hs_store.status(db)


@router.get('/queue')
def queue(country: str | None = None, limit: int = Query(100, ge=1, le=1000), include_confirmed: bool = False, db: Session = Depends(get_db)):
    return hs_store.queue(db, country, limit, include_confirmed)


@router.get('/lookup')
def lookup(country: str, name: str, db: Session = Depends(get_db)):
    return hs.build_index(db).block(country, name)


@router.post('/validate')
def validate(items: list[CheckIn], db: Session = Depends(get_db)):
    index = hs.build_index(db)
    return {'results': [hs.check(item.country, item.name, item.category, item.code, index) for item in items]}


@router.post('/suggest')
def suggest(payload: SuggestIn, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail='Give at least one product.')
    if payload.allow_ai and len(payload.items) > MAX_MODEL_ITEMS:
        raise HTTPException(status_code=400, detail=f'At most {MAX_MODEL_ITEMS} products per call when a model is used.')
    return hs.suggest(db, [item.model_dump() for item in payload.items], allow_peer=payload.allow_peer, allow_ai=payload.allow_ai)


@router.post('/save')
def save(payload: SaveIn, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail='Give at least one code to save.')
    return hs_store.save_assignments(db, [item.model_dump() for item in payload.items], payload.saved_by)
