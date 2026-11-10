"""Assembles the inputs of the shipment functions from the database: a route with its branches, aircraft, provider and built shipments; the prices and tax multipliers of a
shipment's products (from the saved Market Opportunities comparison, and how old that is); the candidates of the Shipment builder. The calculations themselves are in
market.py / allocation.py / finance.py."""

import json

from .. import models
from ..market_opportunities import engine as mo_engine
from ..market_opportunities import staleness
from . import allocation, finance
from .market import UNMATCHED_MARKET_KEY, market_level_for, suggested_sell_price


def _branch(db, branch_id) -> dict | None:
    row = db.get(models.CommercialBranch, branch_id) if branch_id else None
    return {'id': row.id, 'country_id': row.country_id, 'name': row.name, 'airport': row.airport, 'latitude': row.latitude, 'longitude': row.longitude} if row else None


def _aircraft(db, aircraft_id) -> dict | None:
    row = db.get(models.LogisticsAircraft, aircraft_id) if aircraft_id else None
    return {'id': row.id, 'max_payload_kg': row.max_payload_kg, 'cruise_speed_kt': row.cruise_speed_kt, 'short_name': row.short_name} if row else None


def _provider(db, provider_id) -> dict | None:
    row = db.get(models.CharterProvider, provider_id) if provider_id else None
    return {'id': row.id, 'name': row.name, 'block_hour_cost': row.block_hour_cost} if row else None


def locate_country(db, branch: dict | None) -> dict | None:
    """The Market Analysis country (name and region) a branch is in, or None."""
    country = db.get(models.CommercialCountry, branch['country_id']) if branch else None
    region = db.get(models.CommercialRegion, country.region_id) if country else None
    return {'id': country.id, 'name': country.name, 'region': region.name if region else None} if country else None


def destination_markets(db) -> list[dict]:
    from ..routers.market_opportunity_settings import _settings_out

    return _settings_out(db)['destination_markets']


def comparison_info(db, source: str, target: str) -> dict:
    """When the saved comparison the shipment is priced from was calculated, and whether it is out of date (market_opportunities/staleness.py)."""
    rows = db.query(models.MarketOpportunityComparison.calculated_at).filter_by(source_country=source, target_country=target).all()
    calculated = min((row[0] for row in rows if row[0]), default=None)
    status = staleness.pair_status(db, source, target, calculated) if calculated else {'stale': None, 'reasons': []}
    return {'calculated_at': calculated, 'rows': len(rows), 'stale': status['stale'], 'stale_reasons': status['reasons']}


def shipment_context(db, source: str, target: str, items: list[dict]) -> dict:
    """What a shipment's products are priced from: the saved comparison's source / target prices per kg, the tax multipliers of source -> target, and — for products with no match
    in the target market (they are not in the comparison) — the source portfolio's price. -> {prices, multipliers, comparison}"""
    prices = {finance.product_key(row.product_name): {'priceUsdPerKg': row.source_price_normalized, 'targetPriceUsdPerKg': row.target_price_normalized}
              for row in db.query(models.MarketOpportunityComparison).filter_by(source_country=source, target_country=target).all()}
    if any(finance.product_key(item.get('product_name')) not in prices for item in items):
        for product in mo_engine.country_prices(db, source):
            prices.setdefault(finance.product_key(product['name']), {'priceUsdPerKg': product['priceUsdPerKg'], 'targetPriceUsdPerKg': None, 'noMatch': True})
    from ..routers.tax_calculator import list_multipliers

    multipliers = {row['product_key']: row for row in list_multipliers(target, source, db)['multipliers']}
    return {'prices': prices, 'multipliers': multipliers, 'comparison': comparison_info(db, source, target)}


def _shipment(route, leg_key) -> dict | None:
    raw = route.outbound_shipment if leg_key == 'outbound' else route.return_shipment
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _route_dict(route) -> dict:
    return {key: getattr(route, key) for key in ('return_type', 'outbound_target_cargo_pct', 'return_target_cargo_pct', 'return_price_per_kg', 'return_cos_per_kg',
                                                 'outbound_leg_cost_pct', 'return_leg_cost_pct')}


def route_finance(db, route_id: str) -> dict | None:
    """Everything the route table and the shipment cards show for one route, computed on the server: for each leg the air fare per kg, the revenue / COS / profit, and — for a
    built shipment — each product's cost chain, market level and suggested sale price with the shipment totals. The outbound leg's figures need its built shipment; the return
    leg's do not. Each leg also says how old the saved comparison it is priced from is (`comparison.stale`). None for an unknown route."""
    route = db.get(models.RevenueStreamRoute, route_id)
    if route is None:
        return None
    origin, destination, back = _branch(db, route.origin_branch_id), _branch(db, route.destination_branch_id), _branch(db, route.return_branch_id)
    aircraft, provider = _aircraft(db, route.aircraft_id), _provider(db, route.charter_provider_id)
    plain, markets = _route_dict(route), destination_markets(db)
    legs = {}
    for leg_key, leg_from, leg_to in (('outbound', origin, destination), ('return', destination, back)):
        airfare = finance.leg_price_per_kg(plain, leg_key, origin, destination, back, aircraft, provider)
        leg = {'leg': leg_key, 'airfare_per_kg': airfare['value'], 'airfare_note': airfare['note'], 'metrics': finance.compute_route_metrics(leg_from, leg_to, aircraft, provider),
               'figures': None, 'shipment': None, 'countries': None, 'comparison': None, 'error': None}
        shipment = _shipment(route, leg_key)
        if shipment:
            source, target = locate_country(db, leg_from), locate_country(db, leg_to)
            if not source or not target:
                leg['error'] = 'The leg’s airports aren’t in an active Market Analysis country.'
            else:
                leg['countries'] = {'source': source, 'target': target}
                context = shipment_context(db, source['name'], target['name'], shipment['items'])
                result = finance.finance_for_shipment(shipment, context['prices'], context['multipliers'], airfare['value'], markets)
                leg['comparison'] = context['comparison']
                leg['shipment'] = {**{key: value for key, value in shipment.items() if key != 'items'},
                                   'items': [{**item, **entry} for item, entry in zip(shipment['items'], result['items'])], 'ddpTotal': result['ddpTotal'], 'saleTotal': result['saleTotal']}
                if leg_key == 'outbound':
                    leg['figures'] = finance.outbound_leg_finance(shipment, result, airfare['value'], aircraft)
        if leg_key == 'return':
            leg['figures'] = finance.return_leg_finance(plain, origin, destination, back, aircraft, provider)
        legs[leg_key] = leg
    return {'route_id': route.id, 'aircraft': aircraft, 'provider': provider, **legs}


def built_shipment_airfares(db, source_country: str, target_countries: list[str]) -> dict:
    """For Market Opportunities: has a shipment been built (Financial ▸ Revenue ▸ route ▸ Shipment builder) for a source -> target country pair, and what is that route's air fare
    per kg? -> {target: {airfarePerKg, note, routeName}} holding only the targets that have a built shipment; the first route with a usable air fare wins."""
    result = {}
    for route in db.query(models.RevenueStreamRoute).filter(models.RevenueStreamRoute.outbound_shipment.isnot(None)).all():
        if not route.outbound_shipment:
            continue
        origin, destination, back = _branch(db, route.origin_branch_id), _branch(db, route.destination_branch_id), _branch(db, route.return_branch_id)
        source, target = locate_country(db, origin), locate_country(db, destination)
        if not source or source['name'] != source_country or not target or target['name'] not in target_countries:
            continue
        price = finance.leg_price_per_kg(_route_dict(route), 'outbound', origin, destination, back, _aircraft(db, route.aircraft_id), _provider(db, route.charter_provider_id))
        if target['name'] not in result or (result[target['name']]['airfarePerKg'] is None and price['value'] is not None):
            result[target['name']] = {'airfarePerKg': price['value'], 'note': price['note'], 'routeName': f"{origin['airport'] or origin['name']} → {destination['airport'] or destination['name']}"}
    return result


# ---------------------------------------------------------------- Market Opportunities: DDP, market level and sell price beside each product of a pair

def _pair_entry(source_price, airfare_per_kg, multiplier, target_price, markets, matched: bool) -> dict:
    """DDP per kg = (FCA price + air fare) x (1 + tax multiplier), then the Market Level and the suggested sell price (the Shipment builder's own rules). A product with no match in
    the target market is a niche market product by definition (`matched` False)."""
    ddp = (source_price + airfare_per_kg) * (1 + multiplier) if None not in (source_price, airfare_per_kg, multiplier) else None
    if not matched:
        niche = next((market for market in markets if market.get('key') == UNMATCHED_MARKET_KEY), None)
        sell = suggested_sell_price(UNMATCHED_MARKET_KEY, ddp, None, markets)
        return {'ddp': ddp, 'fcaPerKg': source_price, 'multiplier': multiplier, 'level': (niche or {}).get('label') or 'Niche Markets', 'levelNote': '', 'sell': sell['value'], 'sellNote': sell['note']}
    info = market_level_for(ddp, target_price, markets)
    if info['share'] is None:
        level, note = None, ''
    elif not info['configured']:
        level, note = None, f"DDP is {info['share']:.1f}% of the target price. Set the ranges in Settings ▸ Market Opportunity settings ▸ Destination Market."
    else:
        level, note = info['level'], f"DDP is {info['share']:.1f}% of the target price{'' if info['level'] else ' — outside every Destination Market range'}"
    sell = suggested_sell_price(info['key'] if info['share'] is not None and info['configured'] else None, ddp, target_price, markets)
    return {'ddp': ddp, 'fcaPerKg': source_price, 'multiplier': multiplier, 'level': level, 'levelNote': note, 'sell': sell['value'], 'sellNote': sell['note']}


def pair_pricing(db, source_country: str, target_countries: list[str]) -> dict:
    """For each target that has a built shipment: the air fare, and for every product — in the saved comparison (`rows`) or only in the source portfolio (`unmatched`) — its DDP
    price, Market Level and suggested sell price. Keys are `target|product name lowercased`. -> {airfares, rows, unmatched}"""
    airfares = built_shipment_airfares(db, source_country, target_countries)
    markets = destination_markets(db) if airfares else []
    portfolio = {finance.product_key(product['name']): product for product in mo_engine.country_prices(db, source_country)} if airfares else {}
    from ..routers.tax_calculator import list_multipliers

    rows, unmatched = {}, {}
    for target, ship in airfares.items():
        multipliers = {row['product_key']: row['tax_multiplier'] for row in list_multipliers(target, source_country, db)['multipliers']}
        compared = set()
        for row in db.query(models.MarketOpportunityComparison).filter_by(source_country=source_country, target_country=target).all():
            key = finance.product_key(row.product_name)
            compared.add(key)
            rows[f'{target}|{key}'] = _pair_entry(row.source_price_normalized, ship['airfarePerKg'], multipliers.get(key), row.target_price_normalized, markets, True)
        for key, product in portfolio.items():
            if key not in compared:
                unmatched[f'{target}|{key}'] = _pair_entry(product['priceUsdPerKg'], ship['airfarePerKg'], multipliers.get(key), None, markets, False)
    return {'airfares': airfares, 'rows': rows, 'unmatched': unmatched}


# ---------------------------------------------------------------- the Shipment builder's candidates

def candidates(db, source: str, target: str, airfare_per_kg=None) -> dict:
    """The products a route's shipment can be built from: the priority list of source -> target, looked up in the SAVED comparison (compute it first: Market Opportunities),
    each with its rating, Country SAM, market level, cargo cap and margin; priority products with no match in the target market ship as niche products by definition.
    -> {status: 'no_priority' | 'no_comparison' | 'ready', groups, missingPriority, comparison, markets, multipliers}"""
    names = {row.product_name for row in db.query(models.MarketOpportunityPriority).filter_by(source_country=source, target_country=target)}
    if not names:
        return {'status': 'no_priority', 'groups': [], 'missingPriority': [], 'comparison': None}
    comparison = comparison_info(db, source, target)
    all_rows = db.query(models.MarketOpportunityComparison).filter_by(source_country=source, target_country=target).all()
    if not all_rows:
        return {'status': 'no_comparison', 'groups': [], 'missingPriority': sorted(names), 'comparison': comparison}
    rows = [_row_dict(row) for row in all_rows if row.product_name in names]
    not_in_comparison = sorted(names - {row['product_name'] for row in rows})
    portfolio = {finance.product_key(product['name']): product for product in mo_engine.country_prices(db, source)} if not_in_comparison else {}
    unmatched = [portfolio[finance.product_key(name)] for name in not_in_comparison if finance.product_key(name) in portfolio]
    markets = destination_markets(db)
    from ..routers.tax_calculator import list_multipliers

    multipliers = {row['product_key']: row for row in list_multipliers(target, source, db)['multipliers']}
    target_country = db.query(models.CommercialCountry).filter_by(name=target).first()
    region = db.get(models.CommercialRegion, target_country.region_id).name if target_country else None
    codes = sorted({code for code in [*(row['hs_code'] for row in rows), *(product['hsCode'] for product in unmatched)] if code and len(code) == 6 and code.isdigit()})
    sam, sam_error = {}, None
    if codes and region:
        try:
            from ..routers import comtrade

            sam = comtrade.product_sam(region, ','.join(codes), 'M', db).get('products', {})
        except Exception as error:  # noqa: BLE001 — Country SAM is for ordering and default caps; the list still works without it
            sam_error = str(getattr(error, 'detail', None) or error)

    def sam_for(hs_code):
        return ((sam.get(hs_code) or {}).get('countries', {}).get(target) or {}).get('value')

    def level_for(row):
        multiplier = (multipliers.get(finance.product_key(row['product_name'])) or {}).get('tax_multiplier')
        return allocation.product_market_info(row, airfare_per_kg, multiplier, markets, sam_for(row['hs_code']))

    groups = allocation.group_products_by_rating(rows, lambda row: sam_for(row['hs_code']), allocation.ALL_RATINGS, level_for)
    if unmatched:
        niche = next((market for market in markets if market.get('key') == UNMATCHED_MARKET_KEY), None)
        extra = [{'key': f"{product['name']}|{product['hsCode'] or ''}", 'hsCode': product['hsCode'], 'productName': product['name'], 'targetProductName': None, 'diffPct': None,
                  'opportunityRating': 'Unrated', 'countrySam': sam_for(product['hsCode']), 'marketKey': UNMATCHED_MARKET_KEY,
                  'marketLevel': (niche or {}).get('label') or 'Niche Markets', 'capKg': (niche or {}).get('cargo_cap_kg'), 'noMatch': True} for product in unmatched]
        unrated = next((group for group in groups if group['rating'] == 'Unrated'), None)
        if unrated:
            unrated['products'].extend(extra)
        else:
            groups.append({'rating': 'Unrated', 'products': extra})
    return {'status': 'ready', 'groups': groups, 'missingPriority': [name for name in not_in_comparison if finance.product_key(name) not in portfolio], 'comparison': comparison,
            'samError': sam_error, 'countries': {'source': source, 'target': target, 'region': region}}


def _row_dict(row) -> dict:
    return {'product_name': row.product_name, 'target_product_name': row.target_product_name, 'hs_code': row.hs_code, 'diff_pct': row.diff_pct, 'opportunity_rating': row.opportunity_rating,
            'source_price_normalized': row.source_price_normalized, 'target_price_normalized': row.target_price_normalized}
