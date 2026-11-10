"""How the shipment builder picks and sizes the products of a shipment (ported line for line from ShipmentBuilder/shipmentBuilder.js; the written spec of the rules is
docs/shipment_builder_allocation.md). Pure functions over plain dicts.

  candidates:  one comparison row per source product (the best Diff %), filtered and ordered by rating, Country SAM, Diff %
  market info: each candidate's market level, cargo cap and thin-margin cap reduction (`product_market_info`)
  allocation:  wholesalers get their full cap, then premium, the niche products share what is left; weights typed by hand are kept; whole kg."""

import math

from .market import MARKET_PRIORITY, market_level_for, suggested_sell_price

# Only these opportunity ratings are candidates, in this order; Complex, Difficult, Not Viable and unrated products are left out.
SHIPMENT_RATINGS = ['Very High', 'High', 'Challenging']
# Every rating, in the scale's order — for a list the user chose themselves (the priority list), where nothing is left out.
ALL_RATINGS = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable', 'Unrated']
# Most a product can get: one with a known Country SAM, or one whose market size could not be defined.
SAM_CAP_KG = 1500
NO_SAM_CAP_KG = 200


def js_round(value: float) -> int:
    """JavaScript's Math.round: halves go up."""
    return math.floor(value + 0.5)


def best_row_per_product(rows: list[dict]) -> list[dict]:
    """A comparison has a row per matched target product, so the same source product appears several times — keep its best (lowest) Diff %, which also sets its rating."""
    best: dict[str, dict] = {}
    for row in rows:
        key = f"{row['product_name']}|{row.get('hs_code') if row.get('hs_code') is not None else ''}"
        current = best.get(key)
        if current is None or (row['diff_pct'] if row.get('diff_pct') is not None else math.inf) < (current['diff_pct'] if current.get('diff_pct') is not None else math.inf):
            best[key] = row
    return list(best.values())


def group_products_by_rating(rows: list[dict], country_sam_for, ratings=None, extra_for=None) -> list[dict]:
    """[{rating, products}] for each of `ratings` that has products. Within a rating: Country SAM descending (the bigger the target market), then Diff % ascending
    (the lower, the larger the margin); a missing value always sorts last. `extra_for(row)` adds fields to each product (its market level and cargo cap)."""
    ratings = ratings or SHIPMENT_RATINGS
    products = [
        {'key': f"{row['product_name']}|{row.get('hs_code') if row.get('hs_code') is not None else ''}", 'hsCode': row.get('hs_code'), 'productName': row['product_name'],
         'targetProductName': row.get('target_product_name'), 'diffPct': row.get('diff_pct'), 'opportunityRating': row.get('opportunity_rating') or 'Unrated',
         'countrySam': country_sam_for(row), **(extra_for(row) if extra_for else {})}
        for row in best_row_per_product(rows) if (row.get('opportunity_rating') or 'Unrated') in ratings
    ]
    products.sort(key=lambda p: (-(p['countrySam'] if p['countrySam'] is not None else -math.inf), p['diffPct'] if p['diffPct'] is not None else math.inf))
    return [group for group in ({'rating': rating, 'products': [p for p in products if p['opportunityRating'] == rating]} for rating in ratings) if group['products']]


def product_market_info(row: dict, airfare_per_kg, multiplier, destination_markets: list[dict], country_sam) -> dict:
    """The market level, cargo cap and margin of one comparison row as a shipment candidate: the product's DDP price per kg = (source price + air fare) x (1 + tax
    multiplier), as a % of the target price, against the Destination Market ranges. A wholesale product with a thin profit margin ((sale - cost) / cost, the sale price
    being the suggested one) is shipped less: its cap loses the wholesalers' cap reduction. -> {marketKey, marketLevel, capKg, marginPct, capReduced}"""
    source, target = row.get('source_price_normalized'), row.get('target_price_normalized')
    ddp = (source + airfare_per_kg) * (1 + multiplier) if airfare_per_kg is not None and multiplier is not None and source is not None else None
    level = market_level_for(ddp, target, destination_markets)
    key, cap_kg = level['key'], level['cargoCapKg']
    market = next((item for item in destination_markets if item.get('key') == key), None)
    margin_pct, cap_reduced = None, False
    if key == 'wholesalers' and ddp is not None:
        sale = suggested_sell_price(key, ddp, target, destination_markets)['value']
        margin_pct = ((sale - ddp) / ddp) * 100 if sale is not None and ddp > 0 else None
        if margin_pct is not None and market and market.get('min_margin_pct') is not None and market.get('cap_reduction_kg') and margin_pct < market['min_margin_pct']:
            base = cap_kg if cap_kg is not None else (SAM_CAP_KG if (country_sam or 0) > 0 else NO_SAM_CAP_KG)
            cap_kg, cap_reduced = max(0, base - market['cap_reduction_kg']), True
    return {'marketKey': key, 'marketLevel': level['level'], 'capKg': cap_kg, 'marginPct': margin_pct, 'capReduced': cap_reduced}


def _water_fill(items: list[dict], budget: float) -> dict[int, float]:
    """Spreads `budget` kg over `items` (each with a `cap`) as evenly as the caps allow: one common level, so a product below it keeps its own cap and the kilos it does not
    use go to the others. -> {id(item): exact kg}"""
    result: dict[int, float] = {}
    left = max(0, budget)
    by_cap = sorted(items, key=lambda item: item['cap'])
    for index, item in enumerate(by_cap):
        kg = min(item['cap'], left / (len(by_cap) - index))
        result[id(item)] = kg
        left -= kg
    return result


def allocate_shipment(products: list[dict], capacity_kg: float, fixed_kg: dict | None = None) -> dict:
    """Distributes `capacity_kg` over ALL the products (every product of the selection ships), in this order: 1. the wholesalers: every one gets its full cap; 2. the premium
    products: every one gets its full cap; 3. the niche products (and any product with no market level) split what is left evenly, none above its own cap. A product's cap is
    its market's Cargo Cap or SAM_CAP_KG / NO_SAM_CAP_KG. When the aircraft cannot take the full caps the last group to be served gives way. `fixed_kg` (product key -> kg)
    holds weights typed by hand: kept as they are, flagged `manual`, and taken off the capacity first. Whole kg, never above capacity; the kilos lost to rounding go to the
    first products in that order that are still under their cap.
    -> {items: [{...product, kg, sharePct, manual}], allocatedKg, unallocatedKg}"""
    fixed_kg = fixed_kg or {}

    def rank(item):
        return MARKET_PRIORITY.index(item.get('marketKey')) if item.get('marketKey') in MARKET_PRIORITY else len(MARKET_PRIORITY)

    def cap_of(item):
        if item.get('capKg') is not None:
            return item['capKg']
        return SAM_CAP_KG if (item.get('countrySam') or 0) > 0 else NO_SAM_CAP_KG

    manual_items = [{**item, 'kg': math.floor(fixed_kg[item['key']]), 'manual': True} for item in products if item['key'] in fixed_kg]
    budget = max(0, capacity_kg - sum(item['kg'] for item in manual_items))
    ordered = [{**item, 'cap': cap_of(item), 'manual': False} for item in products if item['key'] not in fixed_kg]
    ordered.sort(key=lambda item: (rank(item), -(item['countrySam'] if item.get('countrySam') is not None else -math.inf), item['diffPct'] if item.get('diffPct') is not None else math.inf))

    def sum_caps(items):
        return sum(item['cap'] for item in items)

    wholesalers_key, premium_key = MARKET_PRIORITY[0], MARKET_PRIORITY[1]
    wholesalers = [item for item in ordered if item.get('marketKey') == wholesalers_key]
    premium = [item for item in ordered if item.get('marketKey') == premium_key]
    niche = [item for item in ordered if item.get('marketKey') not in (wholesalers_key, premium_key)]
    exact: dict[int, float] = {}
    after_wholesalers = budget - sum_caps(wholesalers)
    if after_wholesalers <= 0:
        exact.update(_water_fill(ordered, budget))  # the wholesalers alone fill the aircraft: everyone comes down to one common cap
    else:
        for item in wholesalers:
            exact[id(item)] = item['cap']
        after_premium = after_wholesalers - sum_caps(premium)
        if after_premium >= 0:
            for item in premium:
                exact[id(item)] = item['cap']
            exact.update(_water_fill(niche, after_premium))
        else:
            exact.update(_water_fill([*premium, *niche], after_wholesalers))  # the premium caps do not fit after the wholesalers: premium and niche share what is left
    # whole kg: round down, then hand the kilos lost to rounding back, in order, to products under their cap
    sized = [{**item, 'kg': math.floor(exact.get(id(item), 0))} for item in ordered]
    leftover = min(budget, js_round(sum(exact.get(id(item), 0) for item in ordered))) - sum(item['kg'] for item in sized)
    for item in sized:
        if leftover <= 0:
            break
        if item['kg'] < item['cap']:
            item['kg'] += 1
            leftover -= 1
    items = [*manual_items, *[{key: value for key, value in item.items() if key != 'cap'} for item in sized if item['kg'] > 0]]
    allocated = sum(item['kg'] for item in items)
    items = [{**item, 'sharePct': (item['kg'] / allocated) * 100 if allocated else 0} for item in items]
    items.sort(key=lambda item: -item['kg'])
    return {'items': items, 'allocatedKg': allocated, 'unallocatedKg': max(0, js_round(capacity_kg - allocated))}
