"""The Colombia two-source merge: La Mayorista and Corabastos listed once per product id, with each side's price, unit and `norm`, and the derived comparison fields. A line
for line port of `mergeSources` (src/components/company/tabs/OperationsTab/MarketAnalysis/priceComparisonData.js); its output on the frozen inputs is the parity fixture
(backend/tests/fixtures/js_parity/outputs.json, 'colombia_merged'). A full outer join: a product that only one source has is never dropped."""

import math


def per_kg(norm) -> float | None:
    """The price per kg of a `norm` block (in the product's own currency), or None: the only place a price becomes a price per kg (catalog_normalization)."""
    value = norm.get('price_per_kg') if isinstance(norm, dict) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def merge_sources(la_mayorista: list[dict], corabastos: list[dict]) -> list[dict]:
    by_id: dict = {}
    for product in la_mayorista:
        by_id[product.get('id')] = {
            **product,
            'laMayorista': product.get('price'),
            'laMayoristaUnit': product.get('unit'),
            'laMayoristaUnitLabel': product.get('unitLabel') or None,
            'laMayoristaNorm': product.get('norm'),
            'corabastos': None,
            'corabastosUnit': None,
            'corabastosUnitLabel': None,
        }
    for product in corabastos:
        existing = by_id.get(product.get('id'))
        if existing is not None:
            existing['corabastos'] = product.get('price')
            existing['corabastosUnit'] = product.get('unit')
            existing['corabastosUnitLabel'] = product.get('unitLabel') or None
            existing['corabastosNorm'] = product.get('norm')
        else:
            by_id[product.get('id')] = {
                **product,
                'laMayorista': None,
                'laMayoristaUnit': None,
                'laMayoristaUnitLabel': None,
                'corabastos': product.get('price'),
                'corabastosUnit': product.get('unit'),
                'corabastosUnitLabel': product.get('unitLabel') or None,
                'laMayoristaNorm': None,
                'corabastosNorm': product.get('norm'),
            }

    merged = []
    for product in by_id.values():
        la_per_kg, cb_per_kg = per_kg(product.get('laMayoristaNorm')), per_kg(product.get('corabastosNorm'))
        has_la, has_cb = product.get('laMayorista') is not None, product.get('corabastos') is not None
        matched = has_la and has_cb
        source_tag = None if matched else ('La Mayorista only' if has_la else 'Corabastos only')
        # comparable once BOTH sides resolve to a real price per kg (a libra-priced row and a kg-priced one both convert)
        comparable = la_per_kg is not None and cb_per_kg is not None
        diff_pct = ((cb_per_kg - la_per_kg) / la_per_kg) * 100 if comparable and la_per_kg != 0 else None
        is_outlier = comparable and diff_pct is not None and abs(diff_pct) > 100
        cheaper_at = ('la_mayorista' if la_per_kg < cb_per_kg else 'corabastos') if comparable else None
        unit_label = product.get('corabastosUnitLabel') or product.get('laMayoristaUnitLabel') or None
        parts = []
        if has_la:
            parts.append(f"LM: {'kg' if product.get('laMayoristaUnit') == 'kg' else product.get('laMayoristaUnitLabel') or 'other'}")
        if has_cb:
            parts.append(f"CB: {'kg' if product.get('corabastosUnit') == 'kg' else product.get('corabastosUnitLabel') or 'other'}")
        merged.append({
            **product,
            'laMayoristaPerKg': la_per_kg,
            'corabastosPerKg': cb_per_kg,
            'matched': matched,
            'sourceTag': source_tag,
            'comparable': comparable,
            'diffPct': diff_pct,
            'isOutlier': is_outlier,
            'cheaperAt': cheaper_at,
            'unitLabel': unit_label,
            'unitDisplay': 'kg (both)' if matched and comparable else ' · '.join(parts),
        })
    return merged
