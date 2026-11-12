"""The catalog scope API (backend/catalog_normalization/scope.py, scope_store.py): which downloaded products are in the main catalog and which were set aside in the secondary
(discarded) list, with the reason, and the moves between the two. Nothing is deleted and nothing calls the web or a model."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..catalog_normalization import scope, scope_store
from ..database import get_db

router = APIRouter(prefix='/api/catalog-scope', tags=['catalog-scope'])


@router.get('/summary')
def get_summary(db: Session = Depends(get_db)):
    """Tier R. Products in the main catalog and in the secondary list, overall and per source, the reasons for the secondary ones, and how many to check (the rules were unsure)."""
    return scope_store.summary(db)


@router.get('/items')
def get_items(status: str = Query('secondary', pattern='^(main|ready|check|secondary)$'), country: str | None = None, source: str | None = None, q: str | None = None,
              reason: str | None = None, limit: int = Query(200, ge=1, le=scope_store.LIST_LIMIT_MAX), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """Tier R. A portfolio of the three per country: `status=secondary` (the discarded list, the default), `check` (main products with an open issue: no HS code, an old one, no price per kg
    yet, the rules unsure) or `ready` (main, nothing open); `main` is ready + check. Filter by country, source, a text in the name / category, or a reason. The ones the
    rules were unsure about (confidence 'low') come first."""
    return scope_store.listing(db, status, country, source, q, reason, limit, offset)


class ItemRef(BaseModel):
    source: str  # the catalog (snapshot key, e.g. custom_<id>) the list returned
    name: str


class MoveIn(BaseModel):
    items: list[ItemRef]
    to: str = scope.MAIN  # 'main' returns them to the catalog, 'secondary' sends them to the discarded list
    by: str = 'user'


@router.post('/move')
def post_move(payload: MoveIn, db: Session = Depends(get_db)):
    """Tier W. Moves products between the main catalog and the secondary list. The choice is saved (it survives a new download of the catalog) and the catalog is re-annotated;
    the result goes to the data history, so it can be undone there."""
    if payload.to not in (scope.MAIN, scope.SECONDARY):
        raise HTTPException(status_code=400, detail="`to` must be 'main' or 'secondary'.")
    if not payload.items:
        raise HTTPException(status_code=400, detail='Nothing to move.')
    return scope_store.move(db, [item.model_dump() for item in payload.items], payload.to, payload.by)


@router.post('/reclassify')
def post_reclassify(db: Session = Depends(get_db)):
    """Tier W. Applies the current rules (data/scope_rules.json) and the saved choices to every stored supermarket catalog again; appends the result to the data history."""
    return scope_store.reclassify(db)
