"""The money side of a built shipment and of a route (ported line for line from ShipmentBuilder/shipmentFinance.js, ShipmentBuilder/useLegFinance.js and
FinancialTab/routeMetrics.js). Pure functions over plain dicts; `service.py` assembles their inputs from the database.

Cost chain of one product of a built shipment:
  FCA = kg x the origin country's price per kg (the one the saved Market Opportunities comparison used)
  DAP = kg x the leg's price per kg (air fare); DAP subtotal = FCA + DAP
  DDP at Terminal = DAP subtotal x the product's tax multiplier (Market Opportunities origin -> destination); DDP total = DAP subtotal + those taxes
Any figure that cannot be worked out is None."""

import math

from .allocation import js_round
from .market import UNMATCHED_MARKET_KEY, market_level_for, suggested_sell_price

EARTH_RADIUS_NM = 3440.065


def product_key(name) -> str:
    return (name or '').strip().lower()


def js_str(value) -> str:
    """A number as JavaScript writes it inside a template string: 2.0 -> '2', 1.1 -> '1.1'."""
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def thousands(value) -> str:
    """Math.round(value).toLocaleString('en-US')"""
    return f'{js_round(value):,}'


# ---------------------------------------------------------------- the products of a shipment

def costs_for(item: dict, prices: dict | None, multipliers: dict | None, airfare_per_kg) -> dict:
    key = product_key(item.get('product_name'))
    fca_per_kg = (prices or {}).get(key, {}).get('priceUsdPerKg')
    fca = item['kg'] * fca_per_kg if fca_per_kg is not None else None
    dap = item['kg'] * airfare_per_kg if airfare_per_kg is not None else None
    subtotal = fca + dap if fca is not None and dap is not None else None
    multiplier = (multipliers or {}).get(key, {}).get('tax_multiplier')
    taxes = subtotal * multiplier if subtotal is not None and multiplier is not None else None
    ddp = subtotal + taxes if subtotal is not None and taxes is not None else None
    return {'fcaPerKg': fca_per_kg, 'fca': fca, 'dap': dap, 'subtotal': subtotal, 'multiplier': multiplier, 'taxes': taxes, 'ddp': ddp}


def finance_for_shipment(shipment: dict, prices: dict | None, multipliers: dict | None, airfare_per_kg, destination_markets: list[dict]) -> dict:
    """Each product's cost, market level (its DDP per kg as a % of the target price against the Destination Market ranges; a product with no match in the target market is a
    niche market product) and suggested sale price (that level's rule x its weight), and the shipment's totals — None unless every product has one.
    `prices`: {product key -> {priceUsdPerKg, targetPriceUsdPerKg, noMatch?}}, `multipliers`: {product key -> {tax_multiplier}}.
    -> {items: [{cost, level, sale: {perKg, total, note}}] in the shipment's order, ddpTotal, saleTotal}"""
    entries = []
    for item in shipment['items']:
        cost = costs_for(item, prices, multipliers, airfare_per_kg)
        entry = (prices or {}).get(product_key(item.get('product_name')))
        ddp_per_kg = cost['ddp'] / item['kg'] if cost['ddp'] is not None and item['kg'] else None
        target = (entry or {}).get('targetPriceUsdPerKg')
        if (entry or {}).get('noMatch'):
            niche = next((market for market in destination_markets if market.get('key') == UNMATCHED_MARKET_KEY), None)
            level = {'level': (niche or {}).get('label') or 'Niche Markets', 'key': UNMATCHED_MARKET_KEY, 'share': None, 'configured': True, 'noMatch': True}
        else:
            level = market_level_for(ddp_per_kg, target, destination_markets)
        sell = suggested_sell_price(level.get('key'), ddp_per_kg, target, destination_markets)
        entries.append({'cost': cost, 'level': level, 'sale': {'perKg': sell['value'], 'total': sell['value'] * item['kg'] if sell['value'] is not None else None, 'note': sell['note']}})

    def complete(pick):
        return sum(pick(entry) for entry in entries) if entries and all(pick(entry) is not None for entry in entries) else None

    return {'items': entries, 'ddpTotal': complete(lambda entry: entry['cost']['ddp']), 'saleTotal': complete(lambda entry: entry['sale']['total'])}


# ---------------------------------------------------------------- routes

def distance_nm(lat1, lon1, lat2, lon2) -> float:
    """Haversine great-circle distance in nautical miles, rounded to 2 decimals."""
    to_rad = math.radians
    d_lat, d_lon = to_rad(lat2 - lat1), to_rad(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return js_round(EARTH_RADIUS_NM * c * 100) / 100


def block_hours_for(flight_time_hours: float):
    """Rounded up to the next 0.5 h; a whole number of hours stays as it is."""
    whole = math.trunc(flight_time_hours)
    fraction = flight_time_hours - whole
    if fraction == 0:
        return whole
    return whole + 0.5 if fraction <= 0.5 else whole + 1


def compute_route_metrics(origin: dict | None, destination: dict | None, aircraft: dict | None, provider: dict | None) -> dict:
    """One leg, origin -> destination: distance, flight time at the aircraft's cruise speed, block hours and the provider's block-hour cost. Each result is None when the data
    it needs is missing, with the reason in `missing`."""
    missing = []

    def has_coordinates(branch):
        return bool(branch) and branch.get('latitude') is not None and branch.get('longitude') is not None

    if not has_coordinates(origin) or not has_coordinates(destination):
        missing.append('airport coordinates')
    cruise = (aircraft or {}).get('cruise_speed_kt')
    if not cruise or cruise <= 0:
        missing.append("the aircraft's cruise speed")
    hourly_cost = (provider or {}).get('block_hour_cost')
    if hourly_cost is None:
        missing.append("the provider's block-hour cost")
    distance = distance_nm(origin['latitude'], origin['longitude'], destination['latitude'], destination['longitude']) if has_coordinates(origin) and has_coordinates(destination) else None
    flight_time = distance / cruise if distance is not None and cruise and cruise > 0 else None
    block_hours = block_hours_for(flight_time) if flight_time is not None else None
    return {'distanceNm': distance, 'cruiseSpeedKt': cruise, 'flightTimeHours': flight_time, 'blockHours': block_hours, 'blockHourCost': hourly_cost,
            'blockHoursCost': block_hours * hourly_cost if block_hours is not None and hourly_cost is not None else None, 'missing': missing}


def leg_price_per_kg(route: dict, leg_key: str, origin, destination, return_branch, aircraft, provider) -> dict:
    """A leg's Price x Kg (air fare per kg): the whole flight's block-hours cost (both legs) x the leg's cost % (the outbound is 100 % when the return is "full", its return
    leg 0 %) over the leg's available cargo (its target cargo % x the aircraft's max payload). -> {value, note}"""
    if not route.get('return_type'):
        return {'value': None, 'note': 'Select the type of return'}
    outbound = compute_route_metrics(origin, destination, aircraft, provider)
    back = compute_route_metrics(destination, return_branch, aircraft, provider)
    if outbound['blockHoursCost'] is None or back['blockHoursCost'] is None:
        return {'value': None, 'note': 'Needs both legs’ block hours cost'}
    flight_cost = outbound['blockHoursCost'] + back['blockHoursCost']
    is_outbound = leg_key == 'outbound'
    pct = (100 if is_outbound else 0) if route['return_type'] == 'full' else route.get('outbound_leg_cost_pct' if is_outbound else 'return_leg_cost_pct')
    if pct is None:
        return {'value': None, 'note': f'Enter the {leg_key} leg cost %'}
    target_pct = route.get('outbound_target_cargo_pct' if is_outbound else 'return_target_cargo_pct')
    if target_pct is None:
        return {'value': None, 'note': f'Enter the {leg_key} target cargo %'}
    capacity_kg = (aircraft or {}).get('max_payload_kg')
    if not capacity_kg:
        return {'value': None, 'note': "Missing the aircraft's max payload"}
    kg = (target_pct / 100) * capacity_kg
    if not kg:
        return {'value': None, 'note': 'No cargo on this leg'}
    return {'value': (flight_cost * pct) / 100 / kg, 'note': ''}


# ---------------------------------------------------------------- the legs of a route

def _dash(note: str) -> dict:
    return {'revenue': None, 'cos': None, 'profit': None, 'notes': {'revenue': note, 'cos': note, 'profit': note}}


def return_leg_finance(route: dict, origin, destination, return_branch, aircraft, provider) -> dict:
    """Return leg: Revenue = price per kg x the leg's available cargo, where the price per kg is the GSA price x Kg when the return is "full" and the return route's own
    Price x Kg when it is "compensated"; COS = COS x Kg x available cargo; Profit = Revenue - COS. No loading involved."""
    if not route.get('return_type'):
        return _dash('Select the type of return')
    capacity_kg = (aircraft or {}).get('max_payload_kg')
    target_pct = route.get('return_target_cargo_pct')
    missing = []
    if target_pct is None:
        missing.append('the return target cargo %')
    if not capacity_kg:
        missing.append("the aircraft's max payload")
    available_kg = (target_pct / 100) * capacity_kg if target_pct is not None and capacity_kg else None
    full = route['return_type'] == 'full'
    price = None if full else leg_price_per_kg(route, 'return', origin, destination, return_branch, aircraft, provider)
    price_per_kg = route.get('return_price_per_kg') if full else price['value']
    price_note = 'Enter the GSA price x Kg (Add GSA terms)' if full else (price['note'] or 'Needs the return route Price x Kg')
    revenue = price_per_kg * available_kg if price_per_kg is not None and available_kg is not None else None
    cos = route['return_cos_per_kg'] * available_kg if route.get('return_cos_per_kg') is not None and available_kg is not None else None
    profit = revenue - cos if revenue is not None and cos is not None else None

    def needs(parts):
        return f"Needs {' and '.join(parts)}"

    return {
        'revenue': revenue, 'cos': cos, 'profit': profit, 'availableKg': available_kg,
        'notes': {
            'revenue': (f"{'GSA price' if full else 'Return route price'} x Kg {js_str(price_per_kg)} x {thousands(available_kg)} kg available cargo" if revenue is not None
                        else needs([*([price_note] if price_per_kg is None else []), *missing])),
            'cos': (f"COS x Kg {js_str(route['return_cos_per_kg'])} x {thousands(available_kg)} kg available cargo" if cos is not None
                    else needs([*(['the COS x Kg (Add COS)'] if route.get('return_cos_per_kg') is None else []), *missing])),
            'profit': 'Revenue − COS' if profit is not None else 'Needs the revenue and the COS',
        },
    }


def outbound_leg_finance(shipment: dict, finance: dict, airfare_per_kg, aircraft: dict | None) -> dict:
    """Outbound leg: Revenue = the suggested sale prices of the products of its built shipment; COS = what those products cost (DDP); Profit = Revenue - COS - the cost of the
    payload that flies empty ((max payload - kg carried) x the leg's air fare per kg)."""
    carried = sum(item['kg'] for item in shipment['items'])
    capacity = (aircraft or {}).get('max_payload_kg')
    unused_kg = max(0, (capacity if capacity is not None else shipment['capacity_kg']) - carried)
    unused_cost = unused_kg * airfare_per_kg if airfare_per_kg is not None else None
    revenue, cos = finance['saleTotal'], finance['ddpTotal']
    profit = revenue - cos - unused_cost if revenue is not None and cos is not None and unused_cost is not None else None
    waiting = 'Needs every product’s cost and sale price, and the route’s air fare'
    empty_note = f' − {thousands(unused_cost)} USD for the {thousands(unused_kg)} kg of payload flying empty' if profit is not None and unused_kg >= 1 else ''
    return {
        'revenue': revenue, 'cos': cos, 'profit': profit, 'unusedKg': unused_kg, 'unusedCost': unused_cost,
        'notes': {
            'revenue': 'The suggested sale prices of the shipment’s products' if revenue is not None else waiting,
            'cos': 'What the shipment’s products cost (DDP)' if cos is not None else waiting,
            'profit': f'Revenue − COS{empty_note}' if profit is not None else waiting,
        },
    }
