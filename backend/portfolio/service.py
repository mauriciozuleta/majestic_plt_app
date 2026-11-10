"""The product portfolio on the server: every country's products with their English names and HS codes, the directory of one row per country and product, and the
category coverage (which HS chapters / headings / subheadings have products, in which countries, wholesale or retail). A port of the JavaScript that used to build these
in the browser (src/services/productPortfolio.js); its output on the frozen inputs is the parity fixture (backend/tests/fixtures/js_parity/outputs.json).

Read-only. Everything is derived from the stored catalogs, which already carry their `norm` and `hs` blocks (catalog_normalization), so nothing here calls the web or a model."""

import json

from .. import models
from ..catalog_normalization.translate import overrides_from_db, translate_name
from ..snapshot_store import list_snapshots
from .merge import merge_sources

USA_SOURCES = ('usa_beef', 'usa_pork', 'usa_poultry', 'usa_eggs', 'usa_grains', 'usa_produce_fl', 'usa_produce_ca', 'usa_retail_produce')

# The category labels of the directory. A category not listed keeps its own name ("Uncategorized" when it has none). (The old 2-letter category codes of the fallback code
# scheme are gone: a product's code is its country initials + its HS code.)
CATEGORY_LABELS = {
    'pollo': 'Poultry', 'pescados_mariscos': 'Fish & Seafood', 'platanos': 'Plantains', 'tuberculos': 'Tubers', 'frutas': 'Fruits', 'hortalizas': 'Vegetables',
    'carnicos': 'Beef', 'huevos': 'Eggs', 'lacteos': 'Dairy', 'granos_procesados': 'Grains & Processed',
    'Beef': 'Beef', 'Pork': 'Pork', 'Poultry': 'Poultry', 'Eggs': 'Eggs', 'Grains (Export)': 'Grains (Export)',
    'Produce (FL Shipping Point)': 'Produce (FL)', 'Produce (CA Shipping Point)': 'Produce (CA)',
}


def category_label(raw) -> str:
    return CATEGORY_LABELS.get(raw) or raw or 'Uncategorized'


def _products_of(db, source_key: str) -> list[dict]:
    rows = list_snapshots(db, [source_key])
    return rows[0]['products'] if rows and isinstance(rows[0]['products'], list) else []


def colombia_merged(db) -> list[dict]:
    """The merged Colombia table rows, each with its English name: `name_en` (the translation, override > dictionary > fuzzy), `translated`, `translation_tier`."""
    la, cora = _products_of(db, 'la_mayorista'), _products_of(db, 'corabastos')
    if not la and not cora:
        return []
    overrides = overrides_from_db(db)
    rows = []
    for product in merge_sources(la, cora):
        translation = translate_name(product.get('nameEs') or '', overrides)
        rows.append({**product, 'name_en': translation.text, 'translated': translation.translated, 'translation_tier': translation.tier})
    return rows


def country_products(db) -> list[dict]:
    """[{country, products: [{name, category, source_ids, hs}]}] — Colombia (the merged table, in English), the United States (every USDA report), then every source added
    in Settings with its country. `source_ids` says which sources carry the product (a Colombian product can be in both wholesalers)."""
    colombia = [
        {'name': row['name_en'], 'category': row.get('category'),
         'source_ids': [key for key, price in (('la_mayorista', row.get('laMayorista')), ('corabastos', row.get('corabastos'))) if price is not None], 'hs': row.get('hs')}
        for row in colombia_merged(db)
    ]
    # the retail report's per-variety "detail" rows are only the material the commodity rows are built from: the rest of the app (the browser's fetcher did this too) never sees them
    usa = [{'name': product.get('product_en'), 'category': product.get('category'), 'source_ids': [snapshot['source']], 'hs': product.get('hs')}
           for snapshot in list_snapshots(db, list(USA_SOURCES)) for product in snapshot['products'] if not product.get('detail')]
    groups = [{'country': 'Colombia', 'products': colombia}, {'country': 'United States', 'products': usa}]
    for source in db.query(models.ProductSource).filter(models.ProductSource.product_count > 0):
        snapshots = list_snapshots(db, [f'custom_{source.id}'])
        if snapshots:
            groups.append({'country': source.country_name, 'products': [{'name': product.get('name'), 'category': product.get('category'), 'source_ids': [source.id], 'hs': product.get('hs')}
                                                                         for product in snapshots[0]['products']]})
    return groups


def directory(db) -> list[dict]:
    """One row per country and product: {code, name, category, country, countries: [country], hs, label}. `code` and `hs` are None when the product has no HS code (label
    'no_code'); label 'heading_only' is a padded 4-digit heading; 'ok' otherwise. Alphabetical by name, then country."""
    by_key: dict[str, dict] = {}
    for group in country_products(db):
        for product in group['products']:
            name = (product.get('name') or '').strip()
            if not name:
                continue
            key = f"{group['country'].lower()}|{name.lower()}"
            if key not in by_key:
                by_key[key] = {'name': name, 'category': product.get('category'), 'country': group['country'], 'hs': product.get('hs')}
            elif not (by_key[key]['hs'] or {}).get('hs6') and (product.get('hs') or {}).get('hs6'):
                by_key[key]['hs'] = product['hs']
    rows = sorted(by_key.values(), key=lambda row: (row['name'].casefold(), row['country'].casefold()))
    return [{'code': (row['hs'] or {}).get('code'), 'name': row['name'], 'category': category_label(row['category']), 'country': row['country'], 'countries': [row['country']],
             'hs': row['hs'], 'label': (row['hs'] or {}).get('label') or 'no_code'} for row in rows]


def _analysis_types(db) -> dict[str, str]:
    """source id -> 'wholesaler' | 'retail' for the built-in sources (with their saved override) and the sources added in Settings."""
    from ..routers.product_sources import BUILT_IN_SOURCES, DEFAULT_RETAIL_SOURCES

    overrides = {row.source_id: row.analysis_type for row in db.query(models.BuiltInProductSourceOverride).all()}
    types = {keys[0]: overrides.get(keys[0], 'retail' if keys[0] in DEFAULT_RETAIL_SOURCES else 'wholesaler') for _country, _name, _url, keys in BUILT_IN_SOURCES}
    types.update({source.id: source.analysis_type for source in db.query(models.ProductSource).all()})
    return types


def category_coverage(db) -> dict:
    """{chapter: {wholesaler: [iso2], retail: [iso2], productCount, countries, headings: {heading: {wholesaler, retail, subheadings: {subheading: {wholesaler, retail}}}}}}.
    Only chapters / headings / subheadings with at least one product that HAS an HS code appear. A country's ISO2 goes into ONE bucket per product — the deepest level its
    code reaches (a heading-only code stays at the heading) — split wholesaler / retail by the product's own source. The SAM and TAM chapters are the keys of this."""
    codes = {row.name.lower(): row.country_code for row in db.query(models.CountryReferenceCatalog).all()}
    types = _analysis_types(db)
    chapters: dict[str, dict] = {}
    for group in country_products(db):
        country_code = codes.get((group['country'] or '').lower())
        if not country_code:
            continue
        for product in group['products']:
            name = (product.get('name') or '').strip()
            hs = product.get('hs') or {}
            if not name or not hs.get('hs6'):
                continue  # no HS code yet: not part of any category
            code = hs['hs6']
            chapter = chapters.setdefault(code[:2], {'wholesaler': set(), 'retail': set(), 'headings': {}, 'products': set(), 'countries': set()})
            chapter['products'].add(name.lower())
            chapter['countries'].add(country_code)
            heading = chapter['headings'].setdefault(code[:4], {'wholesaler': set(), 'retail': set(), 'subheadings': {}})
            target = heading
            if hs.get('level') != 4:  # a code that is only a padded heading belongs to the heading, not to a made-up subheading
                target = heading['subheadings'].setdefault(code[:6], {'wholesaler': set(), 'retail': set()})
            for source_id in (product.get('source_ids') or [None]):
                target['retail' if types.get(source_id) == 'retail' else 'wholesaler'].add(country_code)

    def listed(buckets):
        return {'wholesaler': sorted(buckets['wholesaler']), 'retail': sorted(buckets['retail'])}

    return {
        chapter_code: {
            **listed(chapter),
            'headings': {
                heading_code: {**listed(heading), 'subheadings': {sub_code: listed(sub) for sub_code, sub in sorted(heading['subheadings'].items())}}
                for heading_code, heading in sorted(chapter['headings'].items())
            },
            'productCount': len(chapter['products']),
            'countries': sorted(chapter['countries']),
        }
        for chapter_code, chapter in sorted(chapters.items())
    }


def qualifying_chapters(db) -> list[str]:
    """The HS chapters SAM / TAM cover: every chapter with a product (what the browser used to ask for from buildCategoryCoverage)."""
    return list(category_coverage(db))
