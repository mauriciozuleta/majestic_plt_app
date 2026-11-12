"""The products of one country, in the shape the comparison works on, whatever pipeline they came from (Colombia's two wholesalers, the USDA reports, a source added in
Settings). A port of the collectors and `consolidateListings` of src/services/marketOpportunities.js. Every product carries:
  matchName, displayName, category, sourceLabel, sourceId, priceValue, priceUnit, priceCurrency, perKgLocal (the price per kg in its OWN currency, None when the unit could
  not be converted), unitComment, norm, hs, translated (only a Colombian name that resolved through the translation), and — when a researched or USDA item weight was used —
  conversionMethod / conversionNote / conversionConfidence."""

import re

from .. import models
from ..catalog_normalization.scope import is_main
from ..catalog_normalization.translate import normalize_name, overrides_from_db, translate_name
from ..portfolio.merge import merge_sources, per_kg
from ..portfolio.service import USA_SOURCES, _analysis_types, _products_of
from ..snapshot_store import list_snapshots

ISO_CURRENCY = re.compile(r'^[A-Z]{3}$')
NOT_CONVERTED = 'This price could not be converted to a price per kg.'


def comment_with_fallback(norm, fallback: str) -> str:
    """The note explaining the figure: the module's note when it produced one, else `fallback` (why there is none)."""
    note = norm.get('note') if isinstance(norm, dict) else None
    if per_kg(norm) is not None and note:
        return note
    return note or fallback


def researched_fields(norm) -> dict:
    """A conversion resting on a researched or USDA item weight is flagged so the comparison row says so and asks for a check."""
    if isinstance(norm, dict) and norm.get('method') in ('researched_item_weight', 'reference_item_weight', 'retail_unit_weight'):
        return {'conversionMethod': norm['method'], 'conversionNote': norm.get('note'), 'conversionConfidence': norm.get('confidence')}
    return {}


def colombia_products(db) -> list[dict]:
    la, cora = _products_of(db, 'la_mayorista'), _products_of(db, 'corabastos')
    if not la and not cora:
        return []
    overrides = overrides_from_db(db)
    products = []
    for p in merge_sources(la, cora):
        if p.get('laMayorista') is None and p.get('corabastos') is None:
            continue
        translation = translate_name(p.get('nameEs') or '', overrides)
        # Colombia has two independent wholesalers; a comparison needs ONE real recorded price per product, never an average: La Mayorista's row is preferred when both
        # have the product (disclosed through sourceLabel), otherwise whichever exists.
        use_la = p.get('laMayorista') is not None
        unit = p.get('laMayoristaUnit') if use_la else p.get('corabastosUnit')
        unit_label = p.get('laMayoristaUnitLabel') if use_la else p.get('corabastosUnitLabel')
        norm = p.get('laMayoristaNorm') if use_la else p.get('corabastosNorm')
        products.append({
            'matchName': normalize_name(translation.text), 'displayName': translation.text, 'category': p.get('category'),
            'sourceLabel': 'La Mayorista' if use_la else 'Corabastos', 'sourceId': 'la_mayorista' if use_la else 'corabastos',
            'priceValue': p.get('laMayorista') if use_la else p.get('corabastos'),
            'priceUnit': 'kg' if unit == 'kg' else (unit_label or unit), 'priceCurrency': 'COP',
            'perKgLocal': per_kg(norm), 'unitComment': comment_with_fallback(norm, NOT_CONVERTED), 'norm': norm, 'hs': p.get('hs'),
            **researched_fields(norm), 'translated': translation.translated, 'rawUnit': unit, 'rawUnitLabel': unit_label,
        })
    return products


def usa_products(db) -> list[dict]:
    products = []
    for snapshot in list_snapshots(db, list(USA_SOURCES)):
        for p in snapshot['products']:
            if p.get('detail'):  # the retail report's per-variety rows are only material for the commodity rows
                continue
            products.append({
                'matchName': normalize_name(p.get('product_en') or ''), 'displayName': p.get('product_en'), 'category': p.get('category'),
                'sourceLabel': snapshot['source'], 'sourceId': snapshot['source'], 'priceValue': p.get('price'), 'priceUnit': p.get('unit'), 'priceCurrency': 'USD',
                'perKgLocal': per_kg(p.get('norm')), 'unitComment': comment_with_fallback(p.get('norm'), NOT_CONVERTED), 'norm': p.get('norm'), 'hs': p.get('hs'),
                **researched_fields(p.get('norm')), 'translated': False,
            })
    return products


def custom_products(db, country: str) -> list[dict]:
    wanted = country.strip().lower()
    currency_by_country = {(row.name or '').strip().lower(): row.currency_code for row in db.query(models.CountryReferenceCatalog).all()}
    # a product's / source's own stated currency when it is a real ISO code; otherwise the country's official currency (a fact of the reference catalog, not a guess)
    fallback = currency_by_country.get(wanted) or None
    products = []
    for source in db.query(models.ProductSource).filter(models.ProductSource.product_count > 0):
        if (source.country_name or '').strip().lower() != wanted:
            continue
        snapshots = list_snapshots(db, [f'custom_{source.id}'])
        if not snapshots:
            continue
        for p in snapshots[0]['products']:
            if not is_main(p):  # discarded by the catalog scope (catalog_normalization/scope.py): not compared, not researched
                continue
            raw = (p.get('currency') or source.currency or '').strip().upper()
            products.append({
                'matchName': normalize_name(p.get('name') or ''), 'displayName': p.get('name'), 'category': p.get('category'), 'sourceLabel': source.name, 'sourceId': source.id,
                'priceValue': p.get('price'), 'priceUnit': p.get('unit'), 'priceCurrency': raw if ISO_CURRENCY.match(raw) else fallback,
                'perKgLocal': per_kg(p.get('norm')), 'unitComment': comment_with_fallback(p.get('norm'), NOT_CONVERTED), 'norm': p.get('norm'), 'hs': p.get('hs'),
                **researched_fields(p.get('norm')), 'translated': False, 'rawUnit': p.get('unit'),
            })
    return products


def consolidate_listings(products: list[dict]) -> list[dict]:
    """A source that reports one product many times (Jamaica's report has a row per parish/market: 680 rows for 154 products) would turn every match into one comparison
    row per listing. Listings of the same product from the same source, price level (category), unit and currency become ONE product: the MEDIAN listing's own recorded
    price (the lower middle one for an even count — never an average), keeping how many listings there were and their range for the row's note."""
    groups: dict[str, list[dict]] = {}
    for product in products:
        key = '|'.join([str(product['sourceId']), (product['displayName'] or '').strip().lower(), str(product.get('category') if product.get('category') is not None else ''),
                        str(product.get('priceUnit') if product.get('priceUnit') is not None else ''), str(product.get('priceCurrency') or '')])
        groups.setdefault(key, []).append(product)
    consolidated = []
    for listings in groups.values():
        if len(listings) == 1:
            consolidated.append(listings[0])
            continue
        ordered = sorted(listings, key=lambda item: item['priceValue'] if item['priceValue'] is not None else float('inf'))
        prices = [item['priceValue'] for item in ordered if item['priceValue'] is not None]
        consolidated.append({**ordered[(len(ordered) - 1) // 2], 'listingCount': len(listings), 'listingLow': prices[0] if prices else None, 'listingHigh': prices[-1] if prices else None})
    return consolidated


def country_products(db, country: str) -> list[dict]:
    """A country's built-in pipeline (Colombia, the United States) and any sources added for it in Settings are combined — an added source never replaces, or is hidden
    by, the built-in one."""
    built_in = colombia_products(db) if country == 'Colombia' else usa_products(db) if country == 'United States' else []
    return consolidate_listings([*built_in, *custom_products(db, country)])


def attach_context(db, products_by_country: dict[str, list[dict]]) -> None:
    """The HS code of each product (the one the normalization module gave it AS SOLD IN ITS COUNTRY) and the price level of its source (Settings ▸ Product analysis
    sources: wholesaler / retail), so a comparison can say when it is wholesale against retail."""
    levels = _analysis_types(db)
    for products in products_by_country.values():
        for index, product in enumerate(products):
            hs = product.get('hs') or {}
            product['hsCode'] = hs.get('hs6') or None
            product['hsDescription'] = hs.get('description') or None
            product['priceLevel'] = levels.get(product['sourceId']) or None
            product['_idx'] = index
