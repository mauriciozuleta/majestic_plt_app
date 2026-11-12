"""The secondary (discarded) catalog: what scope.py sent out of the main catalog, a list a person can consult, and the moves back and forth.

Nothing is deleted: a discarded product stays in its stored catalog with `scope.status == 'secondary'`; moving it means saving the person's choice (table
product_scope_overrides, keyed by catalog + lowercased name so a new download keeps it) and re-annotating that catalog, which appends the result to the data history.
Nothing here calls the web or a model."""

import json
from collections import Counter
from datetime import datetime, timezone

from . import scope
from .catalog import country_of_source, is_catalog_source

LIST_LIMIT_MAX = 1000


def overrides_for(db, source_key: str) -> dict[str, str]:
    """{lowercased product name: 'main' | 'secondary'} chosen by a person for one catalog."""
    from .. import models

    return {row.product_key: row.status for row in db.query(models.ProductScopeOverride).filter_by(source_key=source_key).all()}


def _catalog_rows(db):
    from .. import models

    for row in db.query(models.PriceComparisonSnapshot).all():
        if not is_catalog_source(row.source) or not scope.applies_to(row.source):
            continue
        try:
            products = json.loads(row.data_json)
        except ValueError:
            continue
        if isinstance(products, list):
            yield row, products


def _source_name(db, source_key: str) -> str:
    from .. import models

    source = db.get(models.ProductSource, source_key[len('custom_'):]) if source_key.startswith('custom_') else None
    return source.name if source else source_key


def summary(db) -> dict:
    """The three portfolios, overall and per country / source: `ready` (main, nothing open), `check` (main, with an open issue: no HS code, an old one, no price per kg yet, the rules
    unsure) and `secondary` (discarded, with the reasons); `main` = ready + check."""
    total: Counter = Counter()
    reasons: Counter = Counter()
    sources = []
    for row, products in _catalog_rows(db):
        counts: Counter = Counter()
        for product in products:
            if product.get('detail'):
                continue
            block = product.get('scope') or {}
            status = block.get('status') or scope.MAIN
            counts[status] += 1
            if status == scope.SECONDARY:
                reasons[block.get('reason') or 'unknown'] += 1
            else:
                counts['check' if scope.review_issues(product) else 'ready'] += 1
            if block.get('rule') == 'override':
                counts['moved_by_you'] += 1
        total.update(counts)
        sources.append({'source': row.source, 'name': _source_name(db, row.source), 'country': country_of_source(db, row.source), **{key: counts[key] for key in (scope.MAIN, 'ready', 'check', scope.SECONDARY, 'moved_by_you')}})
    return {'total': {key: total[key] for key in (scope.MAIN, 'ready', 'check', scope.SECONDARY, 'moved_by_you')}, 'reasons': dict(reasons.most_common()), 'sources': sorted(sources, key=lambda s: (s['country'] or '', s['name']))}


def listing(db, status: str = scope.SECONDARY, country: str | None = None, source: str | None = None, query: str | None = None, reason: str | None = None,
            limit: int = 200, offset: int = 0) -> dict:
    """One portfolio: status 'secondary' (the discarded list), 'check' (main products with an open issue), 'ready' (main, nothing open) or 'main' (both). The ones the rules were unsure
    about come first, then by name. -> {total, items: [{source, source_name, country, name, category, price, unit, currency, hs6, status, reason, rule, confidence, per_kg, issues}]}"""
    wanted = (query or '').strip().lower()
    items = []
    for row, products in _catalog_rows(db):
        if source and row.source != source:
            continue
        where = country_of_source(db, row.source)
        if country and (where or '').lower() != country.lower():
            continue
        name_of_source = _source_name(db, row.source)
        for product in products:
            if product.get('detail'):
                continue
            block = product.get('scope') or {'status': scope.MAIN, 'reason': '', 'rule': None, 'confidence': 'high'}
            issues = scope.review_issues(product)
            wanted_status = scope.SECONDARY if status == scope.SECONDARY else scope.MAIN
            if block['status'] != wanted_status or (status == 'check' and not issues) or (status == 'ready' and issues):
                continue
            name = product.get('name') or ''
            if wanted and wanted not in name.lower() and wanted not in (product.get('category') or '').lower():
                continue
            if reason and reason.lower() not in (block.get('reason') or '').lower():
                continue
            items.append({'source': row.source, 'source_name': name_of_source, 'country': where, 'name': name, 'category': product.get('category'), 'price': product.get('price'),
                          'unit': product.get('unit'), 'currency': product.get('currency'), 'hs6': (product.get('hs') or {}).get('hs6'), 'status': block['status'],
                          'reason': block.get('reason'), 'rule': block.get('rule'), 'confidence': block.get('confidence'), 'per_kg': (product.get('norm') or {}).get('price_per_kg'),
                          'issues': [{'code': code, 'label': scope.ISSUES[code]} for code in issues]})
    items.sort(key=lambda item: (item['confidence'] != 'low', -len(item['issues']), item['name'].casefold(), item['source']))
    limit = max(1, min(limit, LIST_LIMIT_MAX))
    return {'total': len(items), 'items': items[max(0, offset):max(0, offset) + limit]}


def move(db, items: list[dict], to: str, by: str = 'user') -> dict:
    """Moves products between the main catalog and the secondary list. items: [{source, name}]. Saves the choice, then re-annotates the catalogs it touched (which appends them
    to the data history). -> {moved, sources, to}"""
    from .. import models
    from ..snapshot_store import record_current
    from .catalog import annotate_with_db

    if to not in (scope.MAIN, scope.SECONDARY):
        raise ValueError("`to` must be 'main' or 'secondary'.")
    now = datetime.now(timezone.utc).isoformat()
    touched: set[str] = set()
    moved = 0
    for item in items:
        source, key = item['source'], scope.product_key(item['name'])
        if not key or not scope.applies_to(source):
            continue
        row = db.get(models.ProductScopeOverride, (source, key))
        if row is None:
            db.add(models.ProductScopeOverride(source_key=source, product_key=key, status=to, set_by=by, set_at=now))
        else:
            row.status, row.set_by, row.set_at = to, by, now
        touched.add(source)
        moved += 1
    db.commit()
    reason = f"{'Returned to the main catalog' if to == scope.MAIN else 'Sent to the secondary list'}: {moved} product(s)"
    for row, products in list(_catalog_rows(db)):
        if row.source in touched:
            annotate_with_db(db, row.source, products)
            row.data_json = json.dumps(products)
    db.commit()
    for source in sorted(touched):
        record_current(db, source, reason)
    return {'moved': moved, 'sources': sorted(touched), 'to': to}


def reclassify(db, reason: str = 'Catalog scope re-applied') -> dict:
    """Applies the current rules (and the saved choices) to every stored supermarket catalog again; appends the result to the data history. Use after editing scope_rules.json."""
    from ..snapshot_store import record_current
    from .catalog import annotate_with_db

    count = 0
    sources = []
    for row, products in list(_catalog_rows(db)):
        annotate_with_db(db, row.source, products)
        row.data_json = json.dumps(products)
        count += len(products)
        sources.append(row.source)
    db.commit()
    for source in sources:
        record_current(db, source, reason)
    return {'products': count, 'sources': len(sources)}


def ensure_scoped(db) -> int:
    """Start-up: supermarket catalogs stored before the scope or review block existed get them once (cheap check first). Returns the products rewritten."""
    lacking = any(products and any(isinstance(product, dict) and ('scope' not in product or 'review' not in product) for product in products[:50]) for _row, products in _catalog_rows(db))
    return reclassify(db, 'Catalog scope added to the stored catalogs')['products'] if lacking else 0
