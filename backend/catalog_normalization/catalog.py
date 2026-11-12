"""Applies the normalization module to the catalogs the app stores (price_comparison_snapshots): every product gets a `norm` dict (and an `hs` block, see hs.py) next to its raw fields —
{price_per_kg, pack_weight_kg, items_per_pack, item_kg, price_per_item, method, confidence, note, sources} — in the product's OWN currency. The raw fields
are never changed, so the legacy frontend conversions keep working until they are retired.

Source families (by snapshot key):
  la_mayorista, corabastos     Colombia: {nameEs, unit: 'kg' | 'other', unitLabel, price}
  usa_*                        USDA AMS: {product_en, unit: 'USD/cwt (100lb)' ..., pack_net_weight_lb, price}
  custom_*                     user-added sources and supermarket catalogs: {name, unit, price}
Anything else (Comtrade caches, ...) is not a product catalog and is left alone."""

import re

from . import scope
from .service import normalize_price
from .store import DbStore
from .translate import overrides_from_db, translate_name
from .units import parse_unit


def is_catalog_source(source_key: str) -> bool:
    return source_key in ('la_mayorista', 'corabastos') or source_key.startswith('usa_') or source_key.startswith('custom_')


# Corabastos presentations that are a box, bag or basket of PRODUCE: their "(N per package)" is the package's net kilograms (caja de 11 = 11 kg of mango), so
# Precio Unidad (Precio Extra / N) is already a price per kg. Checked against La Mayorista's per-kg prices for the same products (banana, mango, pineapple,
# granadilla, lulo, tree tomato, platano, yuca, papaya ...): median ratio 1.1 — read as a price per single piece it would put a banana at 15,553 COP/kg
# against La Mayorista's 2,000. A bunch (ATADO), dozen (DOCENA), roll (ROLLO) or pack (PAQUETE) is a count unit and stays one.
KG_PACKAGE_RE = re.compile(r'^(?:caja(?: de madera)?|canastilla|canasta|bolsa|costal|saco|guacal)\s*\(\d+\s*per package\)$', re.IGNORECASE)
KG_PACKAGE_NOTE = ('Corabastos prices this box/bag/basket per kilogram: its "(N per package)" is the package weight in kg, so the price is already per kg '
                   '(it matches La Mayorista\'s per-kg prices for the same products).')


def _colombia_unit(product: dict) -> str:
    """Corabastos prices a pack presented as '<CONTAINER> (N per package)' per SINGLE item (its 'Precio Unidad' is already Precio Extra / Cantidad), whereas
    '<N> UNIDADES (1 per package)' is the price of the whole N-item pack — the rule documented in countWeightConversion.js; reading '(N per package)' as a
    count of N would shrink the weight-based price N-fold."""
    unit, label = product.get('unit'), (product.get('unitLabel') or '').strip()
    if unit == 'kg':
        return 'kg'
    if KG_PACKAGE_RE.match(label):
        return 'kg'
    if re.match(r'^\d+\s*unidades\b', label, re.IGNORECASE) or parse_unit(label).kind == 'weight':
        return label  # a count pack, or a pack whose weight is written ("25 LIBRAS (1 per package)")
    if re.search(r'\(\d+\s*per package\)', label, re.IGNORECASE):
        # a bunch (ATADO) or roll of herbs/onions is priced per bunch; anything else (a dozen heads ...) per single piece
        return 'per bunch' if re.match(r'^(?:atado|rollo|manojo)\b', label, re.IGNORECASE) else 'each'
    return label


def _usa_unit(product: dict) -> str:
    if isinstance(product.get('pack_net_weight_lb'), (int, float)):
        return f"{product['pack_net_weight_lb']} lb"
    unit = (product.get('unit') or '').strip()
    return re.sub(r'^USD/', '', unit)


def fields_for(source_key: str, product: dict, overrides: dict[str, str] | None = None) -> tuple[str, str, float | None]:
    """(name, unit text, price) the module reads from a stored product of that source. A Colombian product is read under its ENGLISH name (translate.py), so its item
    weight is researched and cached once for the product, not once per language."""
    if source_key in ('la_mayorista', 'corabastos'):
        name_es = product.get('nameEs') or product.get('id') or ''
        return translate_name(name_es, overrides).text, _colombia_unit(product), product.get('price')
    if source_key == 'usa_retail_produce':
        # the weight of one item belongs to the COMMODITY ("Avocados"), not to each variety/pack row ("Avocados (Hass)"): researched and cached once
        return product.get('commodity') or product.get('product_en') or '', _usa_unit(product), product.get('price')
    if source_key.startswith('usa_'):
        return product.get('product_en') or '', _usa_unit(product), product.get('price')
    return product.get('name') or '', product.get('unit') or '', product.get('price')


# HS chapters of products worth researching a per-item weight for: fresh food that is sold by the piece or bunch (meat, fish, eggs/dairy, plants, vegetables, fruit,
# spices, cereals/grains). A packaged good ("Spaghetti | unit") has no standard weight to research: its pack weight is in the name or it stays unconverted.
FRESH_HS_CHAPTERS = {'02', '03', '04', '06', '07', '08', '09', '10', '12'}
GENERIC_UNIT_WORDS = {'', 'unit', 'units', 'item', 'items'}
# Colombian catalog categories that are processed goods, not fresh produce
NON_FRESH_CATEGORIES = {'granos_procesados', 'lacteos', 'procesados', 'aceites', 'abarrotes'}


def researchable(name: str, unit_text: str, hs_chapters: dict[str, str] | None, category: str | None = None) -> bool:
    if (category or '').strip().lower() in NON_FRESH_CATEGORIES:
        return False
    chapter = (hs_chapters or {}).get((name or '').strip().lower())
    if chapter:
        return chapter in FRESH_HS_CHAPTERS
    # not classified (yet): an explicit "each"/"bunch"/"100's" is a produce-style unit; a bare "unit" is the supermarket-catalog default and says nothing
    return (unit_text or '').strip().lower() not in GENERIC_UNIT_WORDS


def hs_chapters_from_db(db) -> dict[str, str]:
    from .. import models

    chapters = {row.product_key: (row.hs_code or '')[:2] for row in db.query(models.ProductHsCode.product_key, models.ProductHsCode.hs_code).all() if row.hs_code}
    for row in db.query(models.ProductHsAssignment.product_key, models.ProductHsAssignment.hs_code).all():  # a code a country's row has wins over the name-only cache
        chapters[row.product_key] = row.hs_code[:2]
    return chapters


def country_of_source(db, source_key: str) -> str | None:
    """The country a snapshot key belongs to (the USDA reports are the United States; a custom source carries its own country)."""
    if source_key in ('la_mayorista', 'corabastos'):
        return 'Colombia'
    if source_key.startswith('usa_'):
        return 'United States'
    if source_key.startswith('custom_'):
        from .. import models

        row = db.get(models.ProductSource, source_key[len('custom_'):])
        return row.country_name if row else None
    return None


def annotate(source_key: str, products: list[dict], store, hs_chapters: dict[str, str] | None = None, overrides: dict[str, str] | None = None, hs_index=None, country: str | None = None,
             scope_overrides: dict[str, str] | None = None) -> list[dict]:
    """Adds `norm` to every product (in place) using only what is known: the text, the researched store and the HS chapter — no web call."""
    if not is_catalog_source(source_key):
        return products
    if source_key == 'usa_retail_produce':
        # the retail report's packs are converted one by one, then ONE store-weighted average row per commodity is rebuilt from them (usa_sources/retail_produce.py)
        from ..usa_sources.retail_produce import consolidate

        details = [product for product in products if product.get('detail')]
        annotate_rows(source_key, details, store, hs_chapters, overrides, hs_index, country, scope_overrides)
        consolidated = consolidate(details)
        annotate_rows(source_key, consolidated, store, hs_chapters, overrides, hs_index, country, scope_overrides)
        products[:] = details + consolidated
        return products
    return annotate_rows(source_key, products, store, hs_chapters, overrides, hs_index, country, scope_overrides)


def annotate_rows(source_key: str, products: list[dict], store, hs_chapters: dict[str, str] | None = None, overrides: dict[str, str] | None = None, hs_index=None, country: str | None = None,
                  scope_overrides: dict[str, str] | None = None) -> list[dict]:
    scoped = scope.applies_to(source_key)
    for product in products:
        name, unit, price = fields_for(source_key, product, overrides)
        if hs_index is not None:  # the product's HS code AS SOLD IN ITS COUNTRY (catalog_normalization/hs.py): looked up, never guessed here
            product['hs'] = hs_index.block(country, name)
        in_catalog = True
        if scoped:  # which products belong in the main catalog (scope.py): the rest keep only what their row states, no weight lookup, no research
            product['scope'] = scope.with_override(scope.classify(product), (scope_overrides or {}).get(scope.product_key(product.get('name') or '')))
            in_catalog = product['scope']['status'] == scope.MAIN
        norm = normalize_price(name, unit, price, store, researchable=in_catalog and researchable(name, unit, hs_chapters, product.get('category')), item_weights=in_catalog).to_dict()
        norm['read_name'], norm['read_unit'] = name, unit  # exactly what the module read: the frontend asks /convert with these after a research
        if source_key in ('la_mayorista', 'corabastos'):
            translation = translate_name(product.get('nameEs') or product.get('id') or '', overrides)
            norm['name_en'], norm['translation'] = translation.text, translation.tier  # 'override' | 'dictionary' | 'fuzzy' | 'none'
            if KG_PACKAGE_RE.match((product.get('unitLabel') or '').strip()):
                norm['note'] = f"{KG_PACKAGE_NOTE} {norm['note']}"
        product['norm'] = norm
        if scoped:  # what this product still needs (scope.py ISSUES): the To check portfolio
            product['review'] = {'issues': scope.review_issues(product)}
    return products


def migrate_weights_to_english(db) -> int:
    """Item weights researched while the Colombian catalogs were still read under their Spanish names are copied to the English key the module uses now (the Spanish
    row is kept). Only an exact dictionary/override translation is used, never a fuzzy one. Returns how many rows were added."""
    from .. import models
    from .store import product_key, signature

    overrides = overrides_from_db(db)
    rows = db.query(models.CatalogItemWeight).all()
    known = {row.signature for row in rows}
    added = 0
    for row in rows:
        translation = translate_name(row.product, overrides)
        if not translation.translated or translation.tier not in ('dictionary', 'override'):
            continue
        new_signature = signature(translation.text, row.count_unit)
        if new_signature in known:
            continue
        db.add(models.CatalogItemWeight(signature=new_signature, product=product_key(translation.text), count_unit=row.count_unit, item_kg=row.item_kg, item_kg_min=row.item_kg_min,
                                        item_kg_max=row.item_kg_max, std_pack_kg=row.std_pack_kg, std_pack_items=row.std_pack_items, confidence=row.confidence,
                                        note=(row.note or '') + f' (researched as "{row.product}")', sources_json=row.sources_json, researched_at=row.researched_at))
        known.add(new_signature)
        added += 1
    db.commit()
    return added


def import_legacy_estimates(db) -> int:
    """The 70 or so whole-pack weights the old Haiku estimator (table product_unit_weight_estimates) cached, copied into the module's store as `priced_unit` weights so no
    paid estimate is lost when that path is retired. The old table is left untouched. Returns how many were added."""
    from .. import models
    from .store import PRICED_UNIT, signature

    known = {row.signature for row in db.query(models.CatalogItemWeight.signature).all()}
    added = 0
    for old in db.query(models.ProductUnitWeightEstimate).all():
        if not old.weight_grams or old.weight_grams <= 0:
            continue
        sig = signature(old.signature, PRICED_UNIT)
        if sig in known:
            continue
        note = f"AI estimate of the whole pack ({old.note or 'no note'}); migrated from the retired Haiku estimator"
        db.add(models.CatalogItemWeight(signature=sig, product=old.signature.strip().lower(), count_unit=PRICED_UNIT, item_kg=old.weight_grams / 1000, confidence='low',
                                        note=note, sources_json='[]', researched_at=old.estimated_at))
        known.add(sig)
        added += 1
    db.commit()
    return added


def annotate_with_db(db, source_key: str, products: list[dict]) -> list[dict]:
    from .hs import build_index

    from .scope_store import overrides_for

    return annotate(source_key, products, DbStore(db), hs_chapters_from_db(db), overrides_from_db(db), build_index(db), country_of_source(db, source_key), overrides_for(db, source_key))
