"""Supermarket catalogs, built by the separate Supermarket_data_fetch app
through its local API (its api_server.py, http://127.0.0.1:8020 by default —
set SUPERMARKET_API_URL to change it). The two apps stay separate: that app
owns the website setups, category discovery and the download itself; this
one asks it for categories, starts a download into a folder chosen here
(backend/supermarket_catalogs/<country>/), follows the job, and when it's
done loads the exported file into the country's product sources with the
same parser a manually uploaded file goes through (custom_sources/extract.py).

No API keys or AI choices are involved on this side; that app runs with its
own AI setup and HS classification switched off in API mode.
"""

import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..custom_sources.extract import SourceError, parse_file
from ..database import SessionLocal, get_db
from .product_sources import _now, _serialize, _store

router = APIRouter()
log = logging.getLogger(__name__)

API_URL = os.environ.get('SUPERMARKET_API_URL', 'http://127.0.0.1:8020').rstrip('/')
CATALOG_DIR = Path(__file__).resolve().parents[1] / 'supermarket_catalogs'
CATALOG_ORIGIN = 'catalog'
UNAVAILABLE = (
    'The supermarket catalog service is not running. Start it with launch_api.bat in the '
    'Supermarket_data_fetch folder, then try again.'
)


class PrepareIn(BaseModel):
    url: str
    country: str


class CategoryIn(BaseModel):
    name: str
    url: str


class SubcategoriesIn(BaseModel):
    store_id: str
    category: CategoryIn
    # The list shown so far — returned merged with what's found, hierarchy rebuilt.
    categories: list[dict] = []


class DownloadIn(BaseModel):
    url: str
    store_id: str
    store_name: str | None = None
    country: str
    categories: list[CategoryIn]
    source_name: str | None = None


def _call(method: str, path: str, payload: dict | None = None, timeout: float = 20) -> dict:
    try:
        response = httpx.request(method, f'{API_URL}{path}', json=payload, timeout=timeout)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from error
    data = response.json() if response.content else {}
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=data.get('error') or 'The catalog service returned an error.')
    return data


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'country'


def _same_url(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.strip().rstrip('/').lower() == b.strip().rstrip('/').lower()


@router.get('/supermarket-catalog/status')
def catalog_status():
    try:
        health = _call('GET', '/health', timeout=3)
        stores = _call('GET', '/stores', timeout=10).get('stores', [])
    except HTTPException as error:
        return {'available': False, 'detail': error.detail, 'api_url': API_URL, 'stores': []}
    return {'available': bool(health.get('ok')), 'detail': None, 'api_url': API_URL, 'stores': stores}


@router.post('/supermarket-catalog/prepare')
def prepare_catalog(payload: PrepareIn):
    if not payload.url.strip() or not payload.country.strip():
        raise HTTPException(status_code=400, detail='Enter the country and the supermarket web address.')
    return _call('POST', '/catalog/prepare', {'url': payload.url.strip(), 'country': payload.country.strip()})


@router.post('/supermarket-catalog/subcategories')
def find_subcategories(payload: SubcategoriesIn):
    """Checks one category's page for sections inside it (the ones a store
    buries under another category), as the desktop app's "Check for
    subcategories" does."""
    return _call('POST', '/catalog/subcategories', payload.model_dump())


@router.post('/supermarket-catalog/download')
def download_catalog(payload: DownloadIn):
    if not payload.categories:
        raise HTTPException(status_code=400, detail='Select at least one category.')
    country = payload.country.strip()
    destination = CATALOG_DIR / _slug(country)
    destination.mkdir(parents=True, exist_ok=True)
    # Echoed back on every poll, so the import still knows where the products
    # belong even if this backend restarted while the download was running.
    client_data = {
        'country': country,
        'url': payload.url.strip(),
        'source_name': (payload.source_name or payload.store_name or payload.store_id).strip(),
        'categories': len(payload.categories),
    }
    job = _call(
        'POST',
        '/catalog/download',
        {
            'url': payload.url.strip(),
            'store_id': payload.store_id,
            'country': country,
            'categories': [category.model_dump() for category in payload.categories],
            'destination': str(destination),
            'client_data': client_data,
        },
    )
    # Imported here when it finishes, whether or not anyone is still
    # watching it (the Settings pop-up can be closed mid-download).
    threading.Thread(target=_watch, args=(job['id'],), name=f'catalog-watch-{job["id"][:8]}', daemon=True).start()
    return job


_imported: dict[str, dict] = {}
_import_lock = threading.Lock()
WATCH_SECONDS = 2
# A download stuck longer than this stops being watched (it can still be
# imported by opening its job again).
WATCH_LIMIT_SECONDS = 6 * 3600


def _importable(job: dict) -> bool:
    """A finished download with an export file — including a cancelled one:
    the service still exports the products it had collected (cancelling
    during the image step loses nothing but the remaining images)."""
    return job.get('kind') == 'download' and job.get('status') in ('done', 'cancelled') and bool((job.get('result') or {}).get('files'))


def _import_once(db: Session, job: dict) -> dict:
    with _import_lock:
        if job['id'] not in _imported:
            _imported[job['id']] = _import(db, job)
        return _imported[job['id']]


def _watch(job_id: str) -> None:
    deadline = time.monotonic() + WATCH_LIMIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(WATCH_SECONDS)
        try:
            job = _call('GET', f'/jobs/{job_id}')
        except HTTPException as error:
            if error.status_code == 404:
                return  # the catalog service restarted and no longer has it
            continue  # service briefly unreachable — keep watching
        if job.get('status') == 'running':
            continue
        if _importable(job):
            db = SessionLocal()
            try:
                result = _import_once(db, job)
                log.info('Supermarket catalog job %s: %s', job_id, result.get('status'))
            except Exception:
                log.exception('Supermarket catalog import failed for job %s', job_id)
            finally:
                db.close()
        return


def _import(db: Session, job: dict) -> dict:
    """Loads a finished download's file into the country's product sources:
    the existing source for this country + web address, or a new Retail one
    (supermarket shelf prices). Same file -> same products, so it's safe to
    run again."""
    meta = job.get('client_data') or {}
    files = [path for path in (job.get('result') or {}).get('files', []) if path.lower().endswith(('.xlsx', '.csv'))]
    if not files:
        return {'status': 'failed', 'error': 'The download finished without an export file.'}
    path = Path(files[0])
    try:
        products = parse_file(path.name, path.read_bytes())
    except (OSError, SourceError) as error:
        return {'status': 'failed', 'error': f'Could not read {path.name}: {error}'}

    source = next(
        (
            row
            for row in db.query(models.ProductSource).filter_by(country_name=meta.get('country'))
            if _same_url(row.url, meta.get('url'))
        ),
        None,
    )
    if source is None:
        source = models.ProductSource(
            id=str(uuid.uuid4()),
            country_name=meta.get('country'),
            name=meta.get('source_name') or 'Supermarket catalog',
            url=meta.get('url'),
            analysis_type='retail',
            status='empty',
            product_count=0,
            created_at=_now(),
        )
        db.add(source)

    summary = (job.get('result') or {}).get('summary') or {}
    failed = summary.get('category_errors') or []
    # API v2: one image per product, saved next to the export (not used by
    # Majestic yet — kept with the file).
    images = summary.get('images') or None
    note = f"Supermarket catalog: {summary.get('categories_completed', 0)} of {len(summary.get('categories_selected') or [])} categories ({path.name})."
    if images:
        note += f" {images.get('downloaded', 0)} of {images.get('total', 0)} product images saved."
    if failed:
        note += f" Incomplete — {len(failed)} categor{'y' if len(failed) == 1 else 'ies'} failed: {', '.join(item['category'] for item in failed)}."
    if job.get('status') == 'cancelled':
        note += ' Cancelled before finishing — the products collected so far were added.'
    _store(db, source, products, CATALOG_ORIGIN, note)
    db.commit()
    return {
        'status': 'imported',
        'source': _serialize(source),
        'product_count': len(products),
        'file': str(path),
        'images': images,
        'partial': job.get('status') == 'cancelled' or bool(failed),
    }


@router.get('/supermarket-catalog/jobs/{job_id}')
def catalog_job(job_id: str, db: Session = Depends(get_db)):
    job = _call('GET', f'/jobs/{job_id}')
    if _importable(job):
        job['import'] = _import_once(db, job)
    return job


@router.post('/supermarket-catalog/jobs/{job_id}/cancel')
def cancel_catalog_job(job_id: str):
    return _call('POST', f'/jobs/{job_id}/cancel')
