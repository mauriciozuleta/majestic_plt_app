"""RAG Files: per-country document folders that are converted to JSON
("Load") and then baked into the country's RAG file ("Bake"). See
rag_files/store.py for the folder layout and statuses and rag_files/convert.py
for the converter (ported and extended from the standalone PDF to RAG tool).

Countries are the distinct countries created in the commercial structure.
"""

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..rag_files import store
from ..rag_files.convert import SUPPORTED_EXTENSIONS, ConversionError

router = APIRouter()


class FileIn(BaseModel):
    filename: str
    content_base64: str


class SearchIn(BaseModel):
    query: str
    top_k: int = 6


def _countries(db: Session) -> list[dict]:
    """Distinct commercial-structure countries by name, with their ISO code."""
    seen: dict[str, dict] = {}
    for row in db.query(models.CommercialCountry).order_by(models.CommercialCountry.name):
        name = (row.name or '').strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = {'name': name, 'country_code': row.country_code}
    return sorted(seen.values(), key=lambda item: item['name'].lower())


def _country(db: Session, name: str) -> str:
    for item in _countries(db):
        if item['name'].lower() == name.strip().lower():
            return item['name']
    raise HTTPException(status_code=404, detail='That country is not in the commercial structure.')


def _detail(country: str) -> dict:
    return {**store.country_summary(country, with_files=True), 'job': store.job_status(country)}


@router.get('/rag-files/countries')
def list_countries(db: Session = Depends(get_db)):
    """Every commercial-structure country with the counts for its card."""
    result = []
    for item in _countries(db):
        summary = store.country_summary(item['name'])
        result.append({**summary, 'country_code': item['country_code'], 'job': store.job_status(item['name'])})
    return {'countries': result, 'supported_extensions': sorted(SUPPORTED_EXTENSIONS)}


@router.get('/rag-files/countries/{name}')
def get_country(name: str, db: Session = Depends(get_db)):
    return _detail(_country(db, name))


@router.post('/rag-files/countries/{name}/files')
def add_file(name: str, payload: FileIn, db: Session = Depends(get_db)):
    country = _country(db, name)
    try:
        data = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail='The file data was not valid.') from error
    try:
        store.save_upload(country, payload.filename, data)
    except ConversionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _detail(country)


@router.delete('/rag-files/countries/{name}/files/{filename}')
def remove_file(name: str, filename: str, db: Session = Depends(get_db)):
    country = _country(db, name)
    if not store.delete_file(country, filename):
        raise HTTPException(status_code=404, detail='File not found.')
    return _detail(country)


@router.get('/rag-files/countries/{name}/files/{filename}/json')
def get_document_json(name: str, filename: str, db: Session = Depends(get_db)):
    """The converted JSON of one loaded file."""
    document = store.read_document(_country(db, name), filename)
    if document is None:
        raise HTTPException(status_code=404, detail='This file has not been loaded yet.')
    return document


@router.post('/rag-files/countries/{name}/load')
def load_files(name: str, db: Session = Depends(get_db)):
    """Queues a Load for the country (it runs when the jobs ahead of it are done)."""
    country = _country(db, name)
    store.enqueue(country, 'load')
    return _detail(country)


@router.post('/rag-files/countries/{name}/bake')
def bake_files(name: str, db: Session = Depends(get_db)):
    """Queues a Bake for the country."""
    country = _country(db, name)
    store.enqueue(country, 'bake')
    return _detail(country)


@router.get('/rag-files/queue')
def get_queue():
    """The running and queued Load/Bake jobs (and the latest finished ones)."""
    return store.queue_snapshot()


@router.post('/rag-files/queue/bake-pending')
def bake_pending(db: Session = Depends(get_db)):
    """Queues a Bake for every country that has loaded documents not yet baked."""
    queued = []
    for item in _countries(db):
        if store.country_summary(item['name'])['needs_bake']:
            queued.append(store.enqueue(item['name'], 'bake')['country'])
    return {'queued': queued, **store.queue_snapshot()}


@router.post('/rag-files/queue/{job_id}/cancel')
def cancel_queued(job_id: str):
    job = store.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='That job is not queued or running.')
    return job


@router.post('/rag-files/countries/{name}/search')
def search_files(name: str, payload: SearchIn, db: Session = Depends(get_db)):
    """Searches the country's baked RAG file (keywords + embeddings)."""
    country = _country(db, name)
    return {'results': store.search_country(country, payload.query, max(1, min(payload.top_k, 20)))}
