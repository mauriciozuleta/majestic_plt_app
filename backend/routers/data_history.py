"""Data history API: the versions of every stored dataset, restore, and the approval of refreshes that looked worse than what is stored.
Storage and rules: backend/data_history/ (store.py, guard.py, service.py)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..data_history import diff as diffs
from ..data_history import service, store
from ..database import get_db

router = APIRouter(prefix='/api/data-history', tags=['data-history'])


class RestoreIn(BaseModel):
    scope: str
    version: int
    restored_by: str = 'user'


class PinIn(BaseModel):
    scope: str
    version: int
    pinned: bool = True


class ResolveIn(BaseModel):
    resolved_by: str = 'user'


@router.get('/datasets')
def datasets(db: Session = Depends(get_db)):
    return [{**row, 'label': service.scope_label(db, row['scope'])} for row in store.scopes()]


@router.get('/log')
def log(scope: str = Query(...)):
    return store.versions(scope)


def _data(scope: str, version: int):
    try:
        return store.load(scope, version)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get('/diff')
def diff(scope: str = Query(...), to: int | None = None, base: int | None = Query(None, alias='from')):
    """Differences between two versions (default: the latest against the one before it)."""
    versions = store.versions(scope)
    if not versions:
        raise HTTPException(status_code=404, detail=f'{scope} has no history.')
    to = to if to is not None else versions[0]['version']
    base = base if base is not None else next((item['version'] for item in versions if item['version'] < to), None)
    new_kind, new = _data(scope, to)
    old_kind, old = _data(scope, base) if base is not None else (None, None)
    return {'scope': scope, 'from': base, 'to': to, **diffs.diff(scope, old_kind, old, new_kind, new)}


@router.post('/restore')
def restore(payload: RestoreIn, db: Session = Depends(get_db)):
    try:
        return service.restore(db, payload.scope, payload.version, payload.restored_by)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post('/pin')
def pin(payload: PinIn):
    if not store.pin(payload.scope, payload.version, payload.pinned):
        raise HTTPException(status_code=404, detail='No such version.')
    return {'ok': True}


@router.get('/held')
def held(status: str | None = 'pending', db: Session = Depends(get_db)):
    """Refreshes parked for approval, each with what approving it would change."""
    items = store.held_updates(status or None)
    for item in items:
        item['label'] = service.scope_label(db, item['scope'])
        if item['status'] == 'pending':
            item['compare'] = service.compare_with_live(db, item['id'])
    return items


@router.post('/held/{held_id}/approve')
def approve(held_id: int, payload: ResolveIn | None = None, db: Session = Depends(get_db)):
    try:
        return service.approve(db, held_id, (payload.resolved_by if payload else 'user'))
    except KeyError as error:
        raise HTTPException(status_code=404, detail='No such held update.') from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post('/held/{held_id}/reject')
def reject(held_id: int, payload: ResolveIn | None = None):
    try:
        return service.reject(held_id, (payload.resolved_by if payload else 'user'))
    except KeyError as error:
        raise HTTPException(status_code=404, detail='No such held update.') from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post('/baseline')
def baseline(db: Session = Depends(get_db)):
    return service.baseline(db)
