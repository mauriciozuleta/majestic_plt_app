"""Deterministic inputs for the shipment functions that moved from JavaScript to backend/shipments/ (Phase 3): grids and seeded random cases that exercise every branch
(missing prices, no match, capped / uncapped markets, manual weights, thin margins, short capacity, ...). capture.py runs the ORIGINAL JavaScript over them and saves both
the inputs and its answers in outputs.json; the Python tests run the same inputs through the port."""

import random

MARKET_SETS = {
    'configured': [
        {'key': 'wholesalers', 'label': 'Wholesalers', 'min': 60, 'max': 100, 'cargo_cap_kg': 500, 'sell_pct': 60, 'min_margin_pct': 15, 'cap_reduction_kg': 100},
        {'key': 'premium', 'label': 'Premium Market', 'min': 30, 'max': 60, 'cargo_cap_kg': 300, 'sell_pct': 20},
        {'key': 'niche', 'label': 'Niche Markets', 'min': 0, 'max': 30, 'cargo_cap_kg': 150, 'sell_pct': 20},
    ],
    'open': [
        {'key': 'wholesalers', 'label': 'Wholesalers', 'min': None, 'max': None, 'cargo_cap_kg': None, 'sell_pct': 60},
        {'key': 'premium', 'label': 'Premium Market', 'min': None, 'max': None, 'cargo_cap_kg': None, 'sell_pct': 20},
        {'key': 'niche', 'label': 'Niche Markets', 'min': None, 'max': None, 'cargo_cap_kg': None, 'sell_pct': 20},
    ],
    'half_open': [
        {'key': 'wholesalers', 'label': 'Wholesalers', 'min': 70, 'max': None, 'cargo_cap_kg': 400, 'sell_pct': 55, 'min_margin_pct': 5, 'cap_reduction_kg': 50},
        {'key': 'premium', 'label': 'Premium Market', 'min': 20, 'max': 70, 'cargo_cap_kg': None, 'sell_pct': 25},
        {'key': 'niche', 'label': 'Niche Markets', 'min': None, 'max': 20, 'cargo_cap_kg': 120, 'sell_pct': None},
    ],
    'empty': [],
}
DDPS = [None, 0, 0.5, 2, 3.5, 6, 9]
TARGETS = [None, 0, 3, 5, 10]
RATINGS = ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable', None]


def market_level():
    return [{'ddp': ddp, 'target': target, 'markets': markets} for markets in MARKET_SETS.values() for ddp in DDPS for target in TARGETS]


def sell_price():
    return [{'key': key, 'ddp': ddp, 'target': target, 'markets': markets}
            for markets in MARKET_SETS.values() for key in ('wholesalers', 'premium', 'niche', 'other', None) for ddp in (None, 1.5, 4) for target in (None, 0, 5, 8)]


def product_info():
    rows = [{'source_price_normalized': 2.0, 'target_price_normalized': 6.0, 'hs_code': '070200'}, {'source_price_normalized': 4.5, 'target_price_normalized': 5.0, 'hs_code': '080440'},
            {'source_price_normalized': None, 'target_price_normalized': 6.0, 'hs_code': None}, {'source_price_normalized': 1.0, 'target_price_normalized': None, 'hs_code': '020130'},
            {'source_price_normalized': 3.0, 'target_price_normalized': 3.0, 'hs_code': '070200'}]
    return [{'row': row, 'params': {'airfarePerKg': airfare, 'multiplier': multiplier, 'destinationMarkets': markets, 'countrySam': sam}}
            for markets in (MARKET_SETS['configured'], MARKET_SETS['half_open'], MARKET_SETS['open']) for row in rows for airfare in (None, 0.8) for multiplier in (None, 0, 0.5)
            for sam in (None, 0, 2_000_000)]


def _product(rng: random.Random, index: int) -> dict:
    return {'key': f'P{index}|{rng.choice(["070200", "080440", ""])}', 'productName': f'P{index}', 'marketKey': rng.choice(['wholesalers', 'wholesalers', 'premium', 'niche', 'niche', None]),
            'capKg': rng.choice([None, 40, 120, 250, 600]), 'countrySam': rng.choice([None, 0, 1_000_000, 8_000_000]), 'diffPct': rng.choice([None, 12.5, 33.3, 48, 71.2])}


def allocate():
    rng = random.Random(2026)
    cases = []
    for n in range(1, 10):
        for capacity in (150, 800, 2500, 12000):
            products = [_product(rng, i) for i in range(n)]
            fixed = [[p['key'], rng.choice([25.7, 100, 333.9])] for p in products[:2]] if rng.random() < 0.4 else []
            cases.append({'products': products, 'capacity': capacity, 'fixed': fixed})
    cases.append({'products': [], 'capacity': 500, 'fixed': []})
    cases.append({'products': [_product(rng, 0)], 'capacity': 0, 'fixed': []})
    return cases


def group():
    rng = random.Random(7)
    rows = []
    for i in range(16):
        rows.append({'product_name': f'Product {i % 11}', 'hs_code': rng.choice(['070200', '080440', None]), 'target_product_name': f'Local {i}', 'diff_pct': rng.choice([None, 8, 15.5, 27, 44, 61, 95, 130]),
                     'opportunity_rating': rng.choice(RATINGS)})
    sam = {'070200': 5_000_000, '080440': 900_000}
    return [{'rows': rows, 'sam': sam, 'ratings': ratings} for ratings in (None, ['Very High', 'High', 'Challenging', 'Complex', 'Difficult', 'Not Viable', 'Unrated'])]


def finance():
    markets = MARKET_SETS['configured']
    prices_full = {'tomato': {'priceUsdPerKg': 2.0, 'targetPriceUsdPerKg': 6.0}, 'beef': {'priceUsdPerKg': 4.5, 'targetPriceUsdPerKg': 5.0},
                   'avocado': {'priceUsdPerKg': 1.0, 'targetPriceUsdPerKg': None, 'noMatch': True}, 'pepper': {'priceUsdPerKg': None, 'targetPriceUsdPerKg': 4.0}}
    multipliers = {'tomato': {'tax_multiplier': 0.5}, 'beef': {'tax_multiplier': 1.2}, 'avocado': {'tax_multiplier': 0}, 'pepper': {'tax_multiplier': 0.3}}
    shipments = [
        {'items': [{'product_name': 'Tomato', 'kg': 400}, {'product_name': 'Beef', 'kg': 300}]},
        {'items': [{'product_name': 'Tomato', 'kg': 400}, {'product_name': 'Avocado', 'kg': 100}, {'product_name': 'Beef', 'kg': 0}]},
        {'items': [{'product_name': 'Pepper', 'kg': 50}, {'product_name': 'Tomato', 'kg': 150}]},
        {'items': [{'product_name': 'Unknown', 'kg': 80}]},
        {'items': []},
    ]
    cases = []
    for shipment in shipments:
        for airfare in (None, 1.2):
            for market_set in ('configured', 'half_open', 'empty'):
                cases.append({'shipment': {**shipment, 'capacity_kg': 1000}, 'prices': prices_full, 'multipliers': multipliers, 'airfare': airfare, 'markets': MARKET_SETS[market_set]})
    cases.append({'shipment': {**shipments[0], 'capacity_kg': 1000}, 'prices': None, 'multipliers': None, 'airfare': 1.2, 'markets': markets})
    return cases


def block_hours():
    return [0, 0.2, 0.5, 0.51, 1, 1.49, 1.5, 2.75, 3.0000001, 7]


COORDS = {'bog': (4.7016, -74.1469), 'kin': (17.9357, -76.7875), 'mia': (25.7959, -80.2870), 'nas': (25.0389, -77.4662), 'none': (None, None)}


def _branch(code):
    lat, lon = COORDS[code]
    return {'latitude': lat, 'longitude': lon}


def distance():
    pairs = [('bog', 'kin'), ('kin', 'mia'), ('mia', 'nas'), ('bog', 'bog'), ('nas', 'bog')]
    return [[*COORDS[a], *COORDS[b]] for a, b in pairs]


def metrics():
    cases = []
    for a, b in (('bog', 'kin'), ('kin', 'none'), ('mia', 'nas')):
        for aircraft in (None, {'cruise_speed_kt': 440, 'max_payload_kg': 18000}, {'cruise_speed_kt': 0, 'max_payload_kg': 18000}):
            for provider in (None, {'block_hour_cost': 5200}, {'block_hour_cost': None}):
                cases.append({'origin': _branch(a), 'destination': _branch(b), 'aircraft': aircraft, 'provider': provider})
    return cases


AIRCRAFT = {'cruise_speed_kt': 440, 'max_payload_kg': 18000}
PROVIDER = {'block_hour_cost': 5200}


def leg_price():
    cases = []
    base = {'outbound_leg_cost_pct': 60, 'return_leg_cost_pct': 40, 'outbound_target_cargo_pct': 90, 'return_target_cargo_pct': 50, 'return_price_per_kg': 1.1, 'return_cos_per_kg': 0.4}
    for return_type in (None, 'full', 'compensated'):
        for mutation in ({}, {'outbound_leg_cost_pct': None}, {'outbound_target_cargo_pct': None}, {'return_target_cargo_pct': 0}):
            for leg in ('outbound', 'return'):
                for aircraft in (AIRCRAFT, {'cruise_speed_kt': 440, 'max_payload_kg': 0}):
                    route = {**base, 'return_type': return_type, **mutation}
                    cases.append({'route': route, 'leg': leg, 'context': {'origin': _branch('bog'), 'destination': _branch('kin'), 'returnBranch': _branch('bog'), 'aircraft': aircraft, 'provider': PROVIDER}})
    cases.append({'route': {**base, 'return_type': 'full'}, 'leg': 'outbound', 'context': {'origin': _branch('bog'), 'destination': _branch('kin'), 'returnBranch': _branch('none'), 'aircraft': AIRCRAFT, 'provider': PROVIDER}})
    return cases


def return_leg():
    cases = []
    base = {'return_target_cargo_pct': 50, 'return_price_per_kg': 1.1, 'return_cos_per_kg': 0.4, 'outbound_leg_cost_pct': 60, 'return_leg_cost_pct': 40, 'outbound_target_cargo_pct': 90}
    context = {'origin': _branch('bog'), 'destination': _branch('kin'), 'returnBranch': _branch('bog'), 'aircraft': AIRCRAFT, 'provider': PROVIDER}
    for return_type in (None, 'full', 'compensated'):
        for mutation in ({}, {'return_price_per_kg': None}, {'return_cos_per_kg': None}, {'return_target_cargo_pct': None}, {'return_price_per_kg': 2}):
            for aircraft in (AIRCRAFT, None):
                cases.append({'route': {**base, 'return_type': return_type, **mutation}, 'context': {**context, 'aircraft': aircraft}})
    return cases


def outbound_leg():
    shipments = finance()
    cases = []
    for index, case in enumerate(shipments):
        if case['prices'] is None:
            continue
        for aircraft in (None, AIRCRAFT):
            cases.append({'finance_case': index, 'aircraft': aircraft})
    return cases


def build() -> dict:
    return {'market_level': market_level(), 'sell_price': sell_price(), 'product_info': product_info(), 'allocate': allocate(), 'group': group(), 'finance': finance(),
            'block_hours': block_hours(), 'distance': distance(), 'metrics': metrics(), 'leg_price': leg_price(), 'return_leg': return_leg(), 'outbound_leg': outbound_leg()}
