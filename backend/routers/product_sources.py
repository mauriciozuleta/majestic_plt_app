"""Settings ▸ Product analysis sources. Lists the built-in sources (Colombia's
two price sheets and the USDA reports, which are code) read-only, and lets the
user add their own. A new source with a web address is analysed on the spot
(custom_sources/extract.py) and its products saved just like the built-in
ones; if the site can't be read — or there's no address — the source waits
for a products file (csv/xlsx/pdf) to be loaded instead.
"""

import base64
import binascii
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..custom_sources.extract import SourceError, analyze_url, parse_file
from ..database import get_db
from ..snapshot_store import list_snapshots, save_snapshot

router = APIRouter()

MAX_FILE_BYTES = 15 * 1024 * 1024

# What the code-defined pipelines pull from (display only — they can't be
# edited from the UI, they're parsers written for those exact pages).
BUILT_IN_SOURCES = [
    ('Colombia', 'La Mayorista', 'https://lamayorista.com.co/', ['la_mayorista']),
    ('Colombia', 'Corabastos daily bulletin', 'https://corabastos.com.co/boletin-precios-corabastos', ['corabastos']),
    ('United States', 'USDA AMS — Beef', 'https://www.ams.usda.gov/market-news', ['usa_beef']),
    ('United States', 'USDA AMS — Pork', 'https://www.ams.usda.gov/market-news', ['usa_pork']),
    ('United States', 'USDA AMS — Poultry', 'https://www.ams.usda.gov/market-news', ['usa_poultry']),
    ('United States', 'USDA AMS — Eggs', 'https://www.ams.usda.gov/market-news', ['usa_eggs']),
    ('United States', 'USDA AMS — Grains (Export)', 'https://www.ams.usda.gov/market-news', ['usa_grains']),
    ('United States', 'USDA AMS — Produce (Florida)', 'https://www.ams.usda.gov/market-news', ['usa_produce_fl']),
    ('United States', 'USDA AMS — Produce (California)', 'https://www.ams.usda.gov/market-news', ['usa_produce_ca']),
]


ANALYSIS_TYPES = ('wholesaler', 'retail')


class SourceIn(BaseModel):
    country_name: str
    name: str
    url: str | None = None
    currency: str | None = None
    analysis_type: str = 'wholesaler'


class SourceFile(BaseModel):
    filename: str
    content_base64: str


class AnalysisTypeIn(BaseModel):
    analysis_type: str


def _built_in_ids() -> set[str]:
    return {keys[0] for _, _, _, keys in BUILT_IN_SOURCES}


def _snapshot_key(source_id: str) -> str:
    return f'custom_{source_id}'


def _serialize(source: models.ProductSource) -> dict:
    return {
        'id': source.id,
        'country_name': source.country_name,
        'name': source.name,
        'url': source.url,
        'currency': source.currency,
        'analysis_type': source.analysis_type,
        'status': source.status,
        'status_message': source.status_message,
        'origin': source.origin,
        'product_count': source.product_count,
        'last_loaded_at': source.last_loaded_at,
        'built_in': False,
    }


def _clean(payload: SourceIn) -> tuple[str, str, str | None, str | None, str]:
    country = payload.country_name.strip()
    name = payload.name.strip()
    url = (payload.url or '').strip() or None
    if not country:
        raise HTTPException(status_code=400, detail='Choose the country this source belongs to.')
    if not name:
        raise HTTPException(status_code=400, detail='Give the source a name.')
    currency = (payload.currency or '').strip().upper() or None
    analysis_type = (payload.analysis_type or '').strip().lower() or 'wholesaler'
    if analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(status_code=400, detail="analysis_type must be 'wholesaler' or 'retail'.")
    return country, name, url, currency, analysis_type


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(db: Session, source: models.ProductSource, products: list[dict], origin: str, note: str) -> None:
    if source.currency:
        for product in products:
            product['currency'] = product.get('currency') or source.currency
    save_snapshot(db, _snapshot_key(source.id), products)
    source.status = 'ok'
    source.status_message = note
    source.origin = origin
    source.product_count = len(products)
    source.last_loaded_at = _now()


def _restamp_currency(db: Session, source: models.ProductSource) -> None:
    snapshots = list_snapshots(db, [_snapshot_key(source.id)])
    if snapshots:
        products = snapshots[0]['products']
        for product in products:
            product['currency'] = source.currency or ''
        save_snapshot(db, _snapshot_key(source.id), products)


def _analyze(db: Session, source: models.ProductSource) -> None:
    """Reads the source's site. On failure the source keeps whatever
    products it already had and asks for a file instead."""
    if source.origin == 'catalog':
        # Built by the supermarket catalog service (routers/supermarket_catalog.py)
        # across many category pages — re-reading just its address here would
        # replace that whole catalog with one page's worth.
        return
    if not source.url:
        if source.product_count == 0:
            source.status, source.status_message = 'empty', 'No web address — load a products file.'
        return
    try:
        products, note = analyze_url(source.url)
    except SourceError as error:
        if source.product_count == 0:
            source.status = 'needs_file'
        source.status_message = f'{error} You can load a products file instead.'
        return
    _store(db, source, products, 'site', note)


@router.get('/product-sources')
def list_product_sources(db: Session = Depends(get_db)):
    built_in_types = {
        row.source_id: row.analysis_type for row in db.query(models.BuiltInProductSourceOverride).all()
    }
    built_in = []
    for country, name, url, keys in BUILT_IN_SOURCES:
        snapshots = list_snapshots(db, keys)
        snapshot = snapshots[0] if snapshots else None
        built_in.append(
            {
                'id': keys[0],
                'country_name': country,
                'name': name,
                'url': url,
                'analysis_type': built_in_types.get(keys[0], 'wholesaler'),
                'status': 'ok' if snapshot else 'empty',
                'status_message': None,
                'origin': 'site',
                'product_count': len(snapshot['products']) if snapshot else 0,
                'last_loaded_at': snapshot['fetched_at'] if snapshot else None,
                'built_in': True,
            }
        )
    custom = db.query(models.ProductSource).order_by(models.ProductSource.country_name, models.ProductSource.created_at).all()
    return {'built_in': built_in, 'custom': [_serialize(source) for source in custom]}


@router.post('/product-sources')
def create_product_source(payload: SourceIn, db: Session = Depends(get_db)):
    country, name, url, currency, analysis_type = _clean(payload)
    source = models.ProductSource(
        id=str(uuid.uuid4()),
        country_name=country,
        name=name,
        url=url,
        currency=currency,
        analysis_type=analysis_type,
        status='empty',
        product_count=0,
        created_at=_now(),
    )
    db.add(source)
    _analyze(db, source)
    db.commit()
    return _serialize(source)


def _get(db: Session, source_id: str) -> models.ProductSource:
    source = db.query(models.ProductSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail='Source not found')
    return source


@router.put('/product-sources/{source_id}')
def update_product_source(source_id: str, payload: SourceIn, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    country, name, url, currency, analysis_type = _clean(payload)
    url_changed = url != source.url
    currency_changed = currency != source.currency
    source.country_name, source.name, source.url, source.currency, source.analysis_type = country, name, url, currency, analysis_type
    if url_changed:
        _analyze(db, source)
    elif currency_changed and source.product_count:
        _restamp_currency(db, source)
    db.commit()
    return _serialize(source)


@router.put('/product-sources/{source_id}/analysis-type')
def set_analysis_type(source_id: str, payload: AnalysisTypeIn, db: Session = Depends(get_db)):
    """Sets just the Wholesaler/Retail label — for a built-in source (which
    has no other editable fields) as well as a custom one (a quick toggle
    from the source list, not requiring the full edit form)."""
    analysis_type = (payload.analysis_type or '').strip().lower()
    if analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(status_code=400, detail="analysis_type must be 'wholesaler' or 'retail'.")

    if source_id in _built_in_ids():
        override = db.query(models.BuiltInProductSourceOverride).filter_by(source_id=source_id).first()
        if override:
            override.analysis_type = analysis_type
        else:
            db.add(models.BuiltInProductSourceOverride(source_id=source_id, analysis_type=analysis_type))
        db.commit()
        return {'id': source_id, 'analysis_type': analysis_type}

    source = _get(db, source_id)
    source.analysis_type = analysis_type
    db.commit()
    return _serialize(source)


@router.post('/product-sources/{source_id}/refresh')
def refresh_product_source(source_id: str, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    if not source.url:
        raise HTTPException(status_code=400, detail='This source has no web address — load a products file instead.')
    if source.origin == 'catalog':
        raise HTTPException(status_code=400, detail='This source is a supermarket catalog — use Rebuild catalog to download it again.')
    _analyze(db, source)
    db.commit()
    return _serialize(source)


@router.post('/product-sources/{source_id}/file')
def load_product_source_file(source_id: str, payload: SourceFile, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail='The file data was not valid.') from error
    if not content:
        raise HTTPException(status_code=400, detail='The file is empty.')
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f'Files are limited to {MAX_FILE_BYTES // (1024 * 1024)} MB.')
    try:
        products = parse_file(payload.filename, content)
    except SourceError as error:
        # Persisted on the row (not just returned as an HTTP error) so the
        # reason is still visible after the frontend reloads the source
        # list — the same "keep whatever it had, explain why" pattern
        # _analyze() uses when a site fetch fails.
        source.status_message = f'{error} (from {payload.filename})'
        if source.product_count == 0:
            source.status = 'needs_file'
        db.commit()
        raise HTTPException(status_code=400, detail=str(error)) from error
    _store(db, source, products, 'file', f'Loaded from {payload.filename}.')
    db.commit()
    return _serialize(source)


@router.delete('/product-sources/{source_id}')
def delete_product_source(source_id: str, db: Session = Depends(get_db)):
    source = _get(db, source_id)
    snapshot = db.query(models.PriceComparisonSnapshot).filter_by(source=_snapshot_key(source.id)).first()
    if snapshot:
        db.delete(snapshot)
    db.delete(source)
    db.commit()
    return {'ok': True}


@router.get('/product-sources/products')
def custom_source_products(db: Session = Depends(get_db)):
    """Every custom source's products, tagged with its country and name, for
    the Country Product Portfolio tab and the General Portfolio Directory."""
    results = []
    for source in db.query(models.ProductSource).filter(models.ProductSource.product_count > 0):
        snapshots = list_snapshots(db, [_snapshot_key(source.id)])
        if not snapshots:
            continue
        results.append(
            {
                'source_id': source.id,
                'source_name': source.name,
                'currency': source.currency,
                'analysis_type': source.analysis_type,
                'country_name': source.country_name,
                'fetched_at': snapshots[0]['fetched_at'],
                'products': snapshots[0]['products'],
            }
        )
    return results
