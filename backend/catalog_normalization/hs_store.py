"""Saving HS assignments, and the two read models behind the review screen: `status` (how many products are in which state) and `queue` (what a person should look at next).
Nothing here calls the web or a model; the suggestions live in hs.py."""

import json
from collections import Counter
from datetime import datetime, timezone

from . import hs
from .catalog import annotate_with_db, country_of_source, is_catalog_source

HISTORY_SCOPE = 'hs:assignments'


def _catalog_rows(db):
    from .. import models

    for row in db.query(models.PriceComparisonSnapshot).all():
        if not is_catalog_source(row.source):
            continue
        try:
            products = json.loads(row.data_json)
        except ValueError:
            continue
        if isinstance(products, list):
            yield row, products


def reannotate_catalogs(db, reason: str) -> int:
    """Rewrites every stored catalog with the current codes (the `hs` block is derived) and appends the result to the data history. Returns the number of products."""
    from ..snapshot_store import record_current

    count = 0
    for row, products in list(_catalog_rows(db)):
        annotate_with_db(db, row.source, products)
        row.data_json = json.dumps(products)
        count += len(products)
    db.commit()
    for row, _products in list(_catalog_rows(db)):
        record_current(db, row.source, reason)
    return count


def ensure_annotated(db) -> int:
    """Start-up: catalogs stored before the `hs` block existed get it once. Cheap check first (does any stored product lack the block?). Returns the products rewritten."""
    lacking = False
    for row, products in _catalog_rows(db):
        if products and any(isinstance(product, dict) and 'hs' not in product for product in products[:50]):
            lacking = True
            break
    return reannotate_catalogs(db, 'HS block added to the stored catalogs') if lacking else 0


def export_assignments(db) -> list[dict]:
    from .. import models

    return [
        {'country': row.country, 'product_key': row.product_key, 'hs_code': row.hs_code, 'hs_level': row.hs_level, 'status': row.status, 'method': row.method,
         'confidence': row.confidence, 'note': row.note, 'assigned_by': row.assigned_by, 'assigned_at': row.assigned_at}
        for row in db.query(models.ProductHsAssignment).order_by(models.ProductHsAssignment.country, models.ProductHsAssignment.product_key)
    ]


def record_history(db, reason: str) -> None:
    """The assignments are curated data: every change is appended to the data history (restorable like any other dataset)."""
    from ..data_history import store

    rows = export_assignments(db)
    if rows:
        store.record(HISTORY_SCOPE, 'json', rows, reason=reason, stats={'assignments': len(rows)})


def replace_assignments(db, rows: list[dict]) -> None:
    """Restore: the table becomes exactly `rows`."""
    from .. import models

    db.query(models.ProductHsAssignment).delete()
    for row in rows:
        db.add(models.ProductHsAssignment(country=row['country'], product_key=row['product_key'], hs_code=row['hs_code'], hs_level=row.get('hs_level') or 6, status=row.get('status') or 'suggested',
                                          method=row.get('method'), confidence=row.get('confidence'), note=row.get('note'), assigned_by=row.get('assigned_by'), assigned_at=row.get('assigned_at')))
    db.commit()


def save_assignments(db, items: list[dict], saved_by: str = 'user') -> dict:
    """items: [{country, name, code, category?, method?, confidence?, note?, status?}]. A code is checked against the reference first; an error refuses just that item.
    A person saving a code makes it 'confirmed' (or 'corrected' when it replaces a different one); `status: 'suggested'` is for code that saves an unreviewed suggestion."""
    from .. import models

    index = hs.build_index(db)
    saved, refused = 0, []
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        country, key = (item.get('country') or '').strip(), hs.hs_key(item.get('name'))
        if not country or not key:
            refused.append({'name': item.get('name'), 'messages': ['A country and a product name are required.']})
            continue
        verdict = hs.check(country, item['name'], item.get('category'), item.get('code'), index)
        if verdict['status'] == 'error':
            refused.append({'name': item['name'], 'country': country, 'messages': verdict['messages']})
            continue
        row = db.get(models.ProductHsAssignment, (country, key))
        previous = row.hs_code if row else (index.legacy.get(key) if (country.lower(), key) not in index.assignments else None)
        wanted = item.get('status') or 'confirmed'
        if wanted == 'confirmed' and previous and hs.parse_code(previous).hs6 != verdict['hs6']:
            wanted = 'corrected'
        if row is None:
            row = models.ProductHsAssignment(country=country, product_key=key)
            db.add(row)
        row.hs_code, row.hs_level, row.status = verdict['hs6'], verdict['level'], wanted
        row.method, row.confidence, row.note = item.get('method') or 'manual', item.get('confidence'), item.get('note')
        row.assigned_by, row.assigned_at = saved_by, now
        saved += 1
    db.commit()
    if saved:
        record_history(db, f'{saved} HS code(s) saved by {saved_by}')
        reannotate_catalogs(db, 'HS codes saved by a person')
    return {'saved': saved, 'refused': refused}


# ---------------------------------------------------------------- read models

def _in_comparison(db) -> set[tuple[str, str]]:
    from .. import models

    return {((row.source_country or '').strip().lower(), (row.product_name or '').strip().lower())
            for row in db.query(models.MarketOpportunityComparison.source_country, models.MarketOpportunityComparison.product_name).all()}


def catalog_products(db):
    """Every distinct (country, English name) of the stored catalogs with its `hs` block and one example row each."""
    seen = {}
    for row, products in _catalog_rows(db):
        country = country_of_source(db, row.source)
        for product in products:
            norm = product.get('norm') or {}
            name = norm.get('read_name') or product.get('name') or product.get('product_en') or ''
            key = hs.hs_key(name)
            if not key or (country, key) in seen:
                continue
            seen[(country, key)] = {'country': country, 'name': name.strip(), 'category': product.get('category'), 'hs': product.get('hs'),
                                    'example': {'source': row.source, 'unit': norm.get('read_unit'), 'price': product.get('price')}}
    return seen


def status(db) -> dict:
    """Per country and overall: products by state (no code / heading only / suggested / confirmed)."""
    per_country: dict[str, Counter] = {}
    for item in catalog_products(db).values():
        block = item['hs'] or {}
        state = 'no_code' if not block.get('hs6') else 'heading_only' if block.get('label') == 'heading_only' else 'confirmed' if block.get('status') in ('confirmed', 'corrected') else 'suggested'
        per_country.setdefault(item['country'] or '—', Counter())[state] += 1
    total = Counter()
    for counts in per_country.values():
        total.update(counts)
    return {'total': dict(total), 'countries': {country: dict(counts) for country, counts in sorted(per_country.items())}}


def queue(db, country: str | None = None, limit: int = 100, include_confirmed: bool = False) -> dict:
    """What a person should look at next: no code, then heading only, then codes with a warning, then the other unreviewed suggestions. Within a group the products that
    are in a saved Market Opportunities comparison come first."""
    index = hs.build_index(db)
    compared = _in_comparison(db)
    rows = []
    for item in catalog_products(db).values():
        if country and (item['country'] or '').lower() != country.lower():
            continue
        block = item['hs'] or {}
        confirmed = block.get('status') in ('confirmed', 'corrected')
        warnings: list[str] = []
        if not block.get('hs6'):
            group = 0
        elif block.get('label') == 'heading_only':
            group = 1
        else:
            verdict = hs.check(item['country'] or '', item['name'], item['category'], block['hs6'], index)
            warnings = verdict['messages']
            group = 4 if confirmed else (2 if warnings else 3)
        if group == 4 and not include_confirmed:
            continue
        rows.append({**item, 'group': group, 'warnings': warnings, 'in_comparison': ((item['country'] or '').lower(), item['name'].lower()) in compared})
    rows.sort(key=lambda r: (r['group'], not r['in_comparison'], r['name'].lower()))
    names = {0: 'no_code', 1: 'heading_only', 2: 'warning', 3: 'unreviewed', 4: 'confirmed'}
    return {'total': len(rows), 'items': [{**r, 'reason': names[r['group']]} for r in rows[:max(1, limit)]]}
