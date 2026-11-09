"""API of the catalog normalization module (backend/catalog_normalization/).

  GET  /api/catalog-normalization/status        per stored catalog: how many products were converted how, and how many are waiting for research
  POST /api/catalog-normalization/reannotate    recompute `norm` on every stored catalog (after new weights were researched, or after the rules changed)
  POST /api/catalog-normalization/research      research the weight of one item for the products that need it — a background job; `dry_run` only counts
  GET  /api/catalog-normalization/weights       every researched item weight
  GET  /api/catalog-normalization/convert       one row: ?name=&unit=&price=  (price per kg, pack weight, items per pack)
  GET  /api/catalog-normalization/items         both directions: ?product=&kg= (items in that weight) or ?product=&count= (weight of those items)
  GET  /api/catalog-normalization/missing-summary   per country: how many products still need an item weight (the red pill of Market Analysis)
  GET  /api/catalog-normalization/missing       ?country= the products of that country with the rows that need a weight (the form behind the pill)
  POST /api/catalog-normalization/validate      checks typed/suggested weights (plausible range, USDA, price per kg against the same product's other listings)
  POST /api/catalog-normalization/suggest       the AI search: researches weights on the web and returns them, validated, WITHOUT saving
  POST /api/catalog-normalization/weights       saves accepted weights to the database and converts every catalog again
"""

import json
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..catalog_normalization.catalog import (annotate_with_db, fields_for, hs_chapters_from_db, import_legacy_estimates, is_catalog_source, migrate_weights_to_english,
                                             researchable)
from ..catalog_normalization.researcher import MAX_ITEMS_PER_BATCH, research_item_weights
from ..catalog_normalization.service import items_in_weight, normalize_price, research_target, weight_of_items
from ..catalog_normalization.store import DbStore, ItemWeight, product_key
from ..catalog_normalization.translate import overrides_from_db
from ..catalog_normalization.units import parse_unit
from ..catalog_normalization.validation import validate_weight
from ..database import SessionLocal, get_db

router = APIRouter()

JOB_MARKER = Path(__file__).resolve().parent.parent / 'catalog_normalization' / '_research_job.marker'
DEFAULT_RESEARCH_LIMIT = 48
# research the catalogs of these sources first (Colombia and the USA feed Market Opportunities), the rest by size
SOURCE_PRIORITY = ('la_mayorista', 'corabastos')


def _source_countries(db: Session) -> dict[str, str]:
    """snapshot key -> country name (the USDA sources are matched by prefix in _country_of)."""
    mapping = {'la_mayorista': 'Colombia', 'corabastos': 'Colombia'}
    for source in db.query(models.ProductSource).all():
        mapping[f'custom_{source.id}'] = source.country_name
    return mapping


def _currency_group(source_key: str) -> str:
    """Sources whose prices share a currency are compared with each other (La Mayorista and Corabastos are both in pesos, every USDA report in dollars); any other source is its own group."""
    if source_key in ('la_mayorista', 'corabastos'):
        return 'COP'
    return 'USD' if source_key.startswith('usa_') else source_key


def _country_of(source_key: str, mapping: dict[str, str]) -> str | None:
    return 'United States' if source_key.startswith('usa_') else mapping.get(source_key)


def _catalog_rows(db: Session):
    rows = db.query(models.PriceComparisonSnapshot).all()
    for row in rows:
        if not is_catalog_source(row.source):
            continue
        try:
            products = json.loads(row.data_json)
        except ValueError:
            continue
        if isinstance(products, list):
            yield row, products


def _needs(db: Session) -> list[dict]:
    """Distinct (product, count unit) pairs still waiting for a researched weight, with the sources that need them, priority sources first."""
    found: dict[tuple[str, str], dict] = {}
    overrides = overrides_from_db(db)
    countries = _source_countries(db)
    for row, products in _catalog_rows(db):
        for product in products:
            norm = product.get('norm') or {}
            if norm.get('method') != 'needs_research':
                continue
            name, unit_text, _price = fields_for(row.source, product, overrides)
            target = research_target(name, parse_unit(unit_text, name))
            if not target:
                continue
            key = (product_key(target[0]), target[1])
            entry = found.setdefault(key, {'product': target[0], 'count_unit': target[1], 'sources': set(), 'countries': set(), 'examples': [], 'rows': 0})
            entry['sources'].add(row.source)
            if _country_of(row.source, countries):
                entry['countries'].add(_country_of(row.source, countries))
            entry['rows'] += 1
            if len(entry['examples']) < 3:
                entry['examples'].append({'label': product.get('nameEs') or product.get('product_en') or product.get('name') or name, 'unit_text': unit_text, 'price': product.get('price'), 'source': row.source})
    ordered = sorted(found.values(), key=lambda e: (0 if e['sources'] & set(SOURCE_PRIORITY) else 1, -e['rows']))
    return [{**e, 'sources': sorted(e['sources']), 'countries': sorted(e['countries'])} for e in ordered]


@router.get('/api/catalog-normalization/status')
def status(db: Session = Depends(get_db)):
    sources = []
    for row, products in _catalog_rows(db):
        methods = Counter((product.get('norm') or {}).get('method', 'not_normalized') for product in products)
        sources.append({'source': row.source, 'products': len(products), 'methods': dict(methods)})
    return {'sources': sources, 'pending_research': len(_needs(db)), 'researching': is_building(JOB_MARKER), 'error': get_error(JOB_MARKER)}


@router.post('/api/catalog-normalization/reannotate')
def reannotate(db: Session = Depends(get_db)):
    migrated = migrate_weights_to_english(db)
    imported = import_legacy_estimates(db)
    count = 0
    for row, products in _catalog_rows(db):
        annotate_with_db(db, row.source, products)
        row.data_json = json.dumps(products)
        count += len(products)
    db.commit()
    return {'products': count, 'weights_copied_to_english_names': migrated, 'legacy_estimates_imported': imported}


class ResearchIn(BaseModel):
    limit: int = DEFAULT_RESEARCH_LIMIT
    dry_run: bool = False
    names: list[str] | None = None  # only these products (as the module reads them: the English name); default: the whole queue


def _run_research(pairs: list[tuple[str, str]]):
    db = SessionLocal()
    try:
        store = DbStore(db)
        for start in range(0, len(pairs), MAX_ITEMS_PER_BATCH):
            batch = pairs[start : start + MAX_ITEMS_PER_BATCH]
            for weight in research_item_weights([(name, unit, '') for name, unit in batch]):
                store.put(weight)
        for row, products in _catalog_rows(db):
            annotate_with_db(db, row.source, products)
            row.data_json = json.dumps(products)
        db.commit()
    except Exception as error:  # noqa: BLE001 — shown to the user through /status
        mark_error(JOB_MARKER, str(error))
    finally:
        db.close()
        clear_building(JOB_MARKER)


@router.post('/api/catalog-normalization/research')
def research(payload: ResearchIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if is_building(JOB_MARKER):
        return {'status': 'already_running'}
    needs = _needs(db)
    if payload.names is not None:
        wanted = {product_key(name) for name in payload.names}
        needs = [entry for entry in needs if product_key(entry['product']) in wanted]
    chosen = needs[: max(0, payload.limit)]
    summary = {'pending': len(needs), 'would_research': len(chosen), 'batches': -(-len(chosen) // MAX_ITEMS_PER_BATCH), 'sample': [f"{e['product']} ({e['count_unit']})" for e in chosen[:8]]}
    if payload.dry_run or not chosen:
        return {'status': 'dry_run' if payload.dry_run else 'nothing_to_do', **summary}
    mark_building(JOB_MARKER)
    background_tasks.add_task(_run_research, [(e['product'], e['count_unit']) for e in chosen])
    return {'status': 'started', **summary}


@router.get('/api/catalog-normalization/weights')
def weights(db: Session = Depends(get_db)):
    rows = db.query(models.CatalogItemWeight).order_by(models.CatalogItemWeight.product).all()
    return {'results': [{'product': r.product, 'count_unit': r.count_unit, 'item_kg': r.item_kg, 'item_kg_min': r.item_kg_min, 'item_kg_max': r.item_kg_max,
                         'std_pack_kg': r.std_pack_kg, 'std_pack_items': r.std_pack_items, 'confidence': r.confidence, 'note': r.note,
                         'sources': json.loads(r.sources_json or '[]'), 'researched_at': r.researched_at} for r in rows]}


@router.get('/api/catalog-normalization/convert')
def convert(name: str, unit: str = '', price: float | None = None, db: Session = Depends(get_db)):
    parsed = parse_unit(unit, name)
    return normalize_price(name, unit, price, DbStore(db), parsed=parsed, researchable=researchable(name, unit, hs_chapters_from_db(db))).to_dict()


@router.get('/api/catalog-normalization/items')
def items(product: str, kg: float | None = Query(None), count: float | None = Query(None), count_unit: str = 'each', db: Session = Depends(get_db)):
    if (kg is None) == (count is None):
        raise HTTPException(status_code=400, detail='Give exactly one of kg (how many items?) or count (what do they weigh?).')
    store = DbStore(db)
    result = items_in_weight(product, kg, store, count_unit) if kg is not None else weight_of_items(product, count, store, count_unit)
    if result is None:
        raise HTTPException(status_code=404, detail=f'The weight of one {count_unit} of "{product}" has not been researched yet.')
    return result


# ---------------------------------------------------------------- missing data of a country: the form behind the red pill of Market Analysis

class ItemIn(BaseModel):
    name: str
    count_unit: str = 'each'
    weight_g: float | None = None
    min_g: float | None = None
    max_g: float | None = None


class ValidateIn(BaseModel):
    items: list[ItemIn]


class SuggestIn(BaseModel):
    items: list[ItemIn]  # at most MAX_ITEMS_PER_BATCH per call


class SaveItem(ItemIn):
    origin: str = 'manual'  # 'manual' | 'ai'
    confidence: str | None = None
    note: str = ''
    sources: list[str] = []


class SaveIn(BaseModel):
    items: list[SaveItem]


def _context_for(db: Session, name: str):
    """(examples, peers) of a product: its own unit-priced listings, and the price per kg of the same product listed with a weight in the SAME source."""
    key = product_key(name)
    examples, sources, stated = [], set(), []
    for row, products in _catalog_rows(db):
        for product in products:
            norm = product.get('norm') or {}
            if product_key(norm.get('read_name') or '') != key:
                continue
            if norm.get('method') == 'needs_research':
                examples.append({'label': product.get('nameEs') or product.get('product_en') or product.get('name') or name, 'price': product.get('price'), 'unit_text': norm.get('read_unit'), 'source': row.source, 'group': _currency_group(row.source)})
                sources.add(_currency_group(row.source))
            elif norm.get('method') in ('stated_weight', 'official_factor') and norm.get('price_per_kg'):
                stated.append({'source': row.source, 'group': _currency_group(row.source), 'per_kg': norm['price_per_kg']})
    return examples, [peer for peer in stated if peer['group'] in sources]


def _validation(db: Session, item: ItemIn) -> dict:
    examples, peers = _context_for(db, item.name)
    weight = item.weight_g / 1000 if item.weight_g else None
    return validate_weight(item.name, item.count_unit, weight, min_kg=item.min_g / 1000 if item.min_g else None, max_kg=item.max_g / 1000 if item.max_g else None,
                           examples=examples, peers=peers).to_dict()


@router.get('/api/catalog-normalization/missing-summary')
def missing_summary(db: Session = Depends(get_db)):
    """{country: number of products whose unit-priced catalog rows still have no item weight} — the number on the red pill."""
    counts = Counter()
    for entry in _needs(db):
        for country in entry['countries']:
            counts[country] += 1
    return {'countries': dict(counts)}


@router.get('/api/catalog-normalization/missing')
def missing(country: str, db: Session = Depends(get_db)):
    items = [entry for entry in _needs(db) if country in entry['countries']]
    return {'country': country, 'items': [{'name': e['product'], 'count_unit': e['count_unit'], 'rows': e['rows'], 'sources': e['sources'], 'examples': e['examples']} for e in items]}


@router.post('/api/catalog-normalization/validate')
def validate(payload: ValidateIn, db: Session = Depends(get_db)):
    return {'results': [_validation(db, item) for item in payload.items]}


@router.post('/api/catalog-normalization/suggest')
def suggest(payload: SuggestIn, db: Session = Depends(get_db)):
    """The AI search of the form: researches the weight of one item on the web for these products and returns it WITHOUT saving anything, each with its validation."""
    if not payload.items:
        return {'results': []}
    if len(payload.items) > MAX_ITEMS_PER_BATCH:
        raise HTTPException(status_code=400, detail=f'At most {MAX_ITEMS_PER_BATCH} products per search.')
    try:
        found = research_item_weights([(item.name, item.count_unit, '') for item in payload.items])
    except Exception as error:  # noqa: BLE001 — the reason (an API problem, for instance) is shown to the person
        raise HTTPException(status_code=502, detail=str(error)) from error
    results = []
    for item, weight in zip(payload.items, found):
        row = {'name': item.name, 'count_unit': item.count_unit, 'weight_g': weight.item_kg * 1000 if weight.item_kg else None,
               'min_g': weight.item_kg_min * 1000 if weight.item_kg_min else None, 'max_g': weight.item_kg_max * 1000 if weight.item_kg_max else None,
               'confidence': weight.confidence, 'note': weight.note, 'sources': weight.sources}
        row['validation'] = _validation(db, ItemIn(name=item.name, count_unit=item.count_unit, weight_g=row['weight_g'], min_g=row['min_g'], max_g=row['max_g']))
        results.append(row)
    return {'results': results}


@router.post('/api/catalog-normalization/weights')
def save_weights(payload: SaveIn, db: Session = Depends(get_db)):
    """Saves the weights a person typed or accepted from the AI search (validated again here: an `error` is refused), then converts every catalog again with them."""
    store = DbStore(db)
    saved, refused = 0, []
    for item in payload.items:
        check = _validation(db, item)
        if check['status'] == 'error':
            refused.append({'name': item.name, 'messages': check['messages']})
            continue
        manual = item.origin == 'manual'
        store.put(ItemWeight(item.name, item.count_unit, item.weight_g / 1000, item.min_g / 1000 if item.min_g else None, item.max_g / 1000 if item.max_g else None,
                             confidence='user' if manual else (item.confidence or 'low'),
                             note=(item.note + ' ' if item.note else '') + ('Entered by a person.' if manual else 'Suggested by the AI search and accepted by a person.'),
                             sources=item.sources))
        saved += 1
    for row, products in _catalog_rows(db):
        annotate_with_db(db, row.source, products)
        row.data_json = json.dumps(products)
    db.commit()
    return {'saved': saved, 'refused': refused, 'still_missing': len(_needs(db))}
