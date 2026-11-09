"""Deleting products from the product catalog (the Country Product Portfolio tables). Products live inside each source's stored snapshot, so a
deletion rewrites that snapshot without the selected rows (its fetched_at stays) and records a modification report (modification_reports.py)."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..modification_reports import write_deletion_report
from ..snapshot_store import list_snapshots

router = APIRouter()

NAME_FIELDS = ('name', 'nameEs', 'product_en')
BUILT_IN_LABELS = {
    'la_mayorista': ('Colombia', 'La Mayorista'),
    'corabastos': ('Colombia', 'Corabastos'),
}
IDENTITY_FIELDS = ('id', 'category', 'unit', 'detail', 'pack')


class CatalogItem(BaseModel):
    source: str  # the snapshot key: la_mayorista, usa_beef, custom_<id> …
    id: str | int | None = None
    category: str | None = None
    name: str | None = None
    unit: str | None = None
    detail: bool | str | None = None
    pack: str | None = None


class DeleteRequest(BaseModel):
    items: list[CatalogItem]
    deleted_by: str = ''


def _describe_source(db: Session, key: str) -> tuple[str, str, models.ProductSource | None]:
    if key in BUILT_IN_LABELS:
        return (*BUILT_IN_LABELS[key], None)
    if key.startswith('usa_'):
        return 'United States', 'USDA — ' + key[4:].replace('_', ' ').title(), None
    if key.startswith('custom_'):
        source = db.get(models.ProductSource, key[len('custom_'):])
        if source:
            return source.country_name, source.name, source
    return '', key, None


def _name_of(product: dict) -> str:
    for field in NAME_FIELDS:
        if product.get(field):
            return str(product[field])
    return ''


def _same(a, b) -> bool:
    return ('' if a is None else str(a)) == ('' if b is None else str(b))


def _matches(product: dict, item: CatalogItem) -> bool:
    """Every identity field the caller sent (null included: "this field is empty") has to equal the product's; the name ignores case."""
    if item.name is not None and _name_of(product).strip().lower() != item.name.strip().lower():
        return False
    return all(_same(product.get(field), getattr(item, field)) for field in IDENTITY_FIELDS if field in item.model_fields_set)


@router.post('/catalog-products/delete')
def delete_catalog_products(payload: DeleteRequest, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail='Select at least one product.')
    by_source: dict[str, list[CatalogItem]] = {}
    for item in payload.items:
        by_source.setdefault(item.source, []).append(item)

    snapshots = {snapshot['source']: snapshot for snapshot in list_snapshots(db, list(by_source))}
    removed: list[dict] = []
    plan = []  # (source key, kept products, ProductSource) — written only after every source is read
    for key, items in by_source.items():
        snapshot = snapshots.get(key)
        if not snapshot or not isinstance(snapshot['products'], list):
            raise HTTPException(status_code=404, detail=f'No stored products for the source "{key}".')
        country, source_name, source_model = _describe_source(db, key)
        kept = []
        for product in snapshot['products']:
            if isinstance(product, dict) and any(_matches(product, item) for item in items):
                norm = product.get('norm') or {}
                removed.append(
                    {
                        'country': country,
                        'source': source_name,
                        'category': product.get('category'),
                        'name': _name_of(product),
                        'unit': product.get('unit'),
                        'price': product.get('price'),
                        'currency': product.get('currency') or '',
                        'per_kg': norm.get('price_per_kg'),
                        'id': product.get('id'),
                    }
                )
            else:
                kept.append(product)
        plan.append((key, kept, source_model))

    if not removed:
        raise HTTPException(status_code=404, detail='None of the selected products is in the database any more.')

    for key, kept, source_model in plan:
        row = db.query(models.PriceComparisonSnapshot).filter_by(source=key).first()
        row.data_json = json.dumps(kept)
        if source_model is not None:
            source_model.product_count = len(kept)
    db.commit()

    path, title = write_deletion_report(removed, len(payload.items), payload.deleted_by)
    from .knowledge_base import sync_reports  # late import: knowledge_base imports the report folder from the module above

    sync_reports(db)
    return {'removed': len(removed), 'requested': len(payload.items), 'report': path.name, 'title': title}
