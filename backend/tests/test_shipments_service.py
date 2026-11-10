"""The database-aware shipment service: a route with its branches, aircraft, provider and built shipment; the prices and tax multipliers a shipment is priced from; the
Shipment builder's candidates; and the endpoints. The numbers are worked out by hand in the comments."""

import json
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base, get_db
from backend.market_opportunities import engine as mo_engine
from backend.routers import comtrade
from backend.routers import shipments as shipments_router
from backend.shipments import finance, service

NOW = '2026-11-10T00:00:00+00:00'
MARKETS = [
    {'key': 'wholesalers', 'label': 'Wholesalers', 'min': 60, 'max': 100, 'cargo_cap_kg': 500, 'sell_pct': 60, 'min_margin_pct': 15, 'cap_reduction_kg': 100},
    {'key': 'premium', 'label': 'Premium Market', 'min': 30, 'max': 60, 'cargo_cap_kg': 300, 'sell_pct': 20},
    {'key': 'niche', 'label': 'Niche Markets', 'min': 0, 'max': 30, 'cargo_cap_kg': 150, 'sell_pct': 20},
]


class ShipmentServiceTests(unittest.TestCase):
    def setUp(self):
        database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(database)
        self.db = sessionmaker(bind=database)()
        self.addCleanup(self.db.close)
        db = self.db
        db.add_all([
            models.CommercialRegion(id='r1', company_id='c1', name='Caribbean'),
            models.CommercialCountry(id='co', company_id='c1', region_id='r1', name='Colombia', country_code='CO'),
            models.CommercialCountry(id='jm', company_id='c1', region_id='r1', name='Jamaica', country_code='JM'),
            models.CommercialBranch(id='bog', company_id='c1', country_id='co', name='Bogota', airport='BOG', latitude=4.7016, longitude=-74.1469),
            models.CommercialBranch(id='kin', company_id='c1', country_id='jm', name='Kingston', airport='KIN', latitude=17.9357, longitude=-76.7875),
            models.LogisticsAircraft(id='ac', company_id='c1', manufacturer='B', model='767', short_name='B767F', mtow_kg=1, empty_weight_kg=1, max_payload_kg=10000, zero_fuel_kg=1,
                                     fuel_capacity_gal=1, fuel_burn_gal_hr=1, cargo_positions_main_deck=1, cargo_positions_lower_deck=1, cruise_speed_kt=440, created_at=NOW),
            models.CharterProvider(id='pv', company_id='c1', name='Charter', country_name='Colombia', aircraft_id='ac', provider_type='charter', block_hour_cost=5000, created_at=NOW),
            models.MarketOpportunitySettings(id='singleton', destination_markets_json=json.dumps(MARKETS)),
            # Tomato: 1.00 USD/kg in Colombia, 6.00 in Jamaica; its tax multiplier 0.5
            models.MarketOpportunityComparison(id='x1', product_name='Tomato', target_product_name='Tomato (local)', source_country='Colombia', target_country='Jamaica', hs_code='070200',
                                               source_price_normalized=1.0, target_price_normalized=6.0, diff_pct=16.7, opportunity_rating='Very High', calculated_at=NOW),
            models.ProductTaxMultiplier(destination='Jamaica', origin='Colombia', product_key='tomato', product_name='Tomato', status='ok', tax_multiplier=0.5, landed_multiplier=1.5, computed_at=NOW),
        ])
        shipment = {'capacity_kg': 10000, 'aircraft_name': 'B767F', 'built_at': NOW, 'items': [{'product_name': 'Tomato', 'hs_code': '070200', 'kg': 400}]}
        db.add(models.RevenueStreamRoute(id='rt', stream_id='s1', origin_branch_id='bog', destination_branch_id='kin', return_branch_id='bog', charter_provider_id='pv', aircraft_id='ac',
                                         return_type='full', outbound_target_cargo_pct=100, return_target_cargo_pct=50, return_price_per_kg=1.1, return_cos_per_kg=0.4,
                                         outbound_shipment=json.dumps(shipment), created_at=NOW))
        db.commit()

    def airfare(self):
        metrics = finance.compute_route_metrics({'latitude': 4.7016, 'longitude': -74.1469}, {'latitude': 17.9357, 'longitude': -76.7875}, {'cruise_speed_kt': 440}, {'block_hour_cost': 5000})
        return 2 * metrics['blockHoursCost'] / 10000  # both legs, 100% of the flight on the outbound ("full" return), over the 10,000 kg of available cargo

    def test_a_route_is_priced_from_its_saved_comparison_and_the_hand_worked_numbers(self):
        result = service.route_finance(self.db, 'rt')
        outbound = result['outbound']
        airfare = outbound['airfare_per_kg']
        self.assertAlmostEqual(airfare, self.airfare())
        self.assertTrue(1.0 < airfare < 5.0)  # BOG-KIN is about 1,000 nm: 2.5 block hours each way at USD 5,000
        item = outbound['shipment']['items'][0]
        # FCA = 400 x 1.00 = 400; DAP = 400 x air fare; taxes = 50% of the subtotal; DDP = 1.5 x subtotal
        self.assertAlmostEqual(item['cost']['fca'], 400.0)
        self.assertAlmostEqual(item['cost']['subtotal'], 400 + 400 * airfare)
        self.assertAlmostEqual(item['cost']['ddp'], (400 + 400 * airfare) * 1.5)
        ddp_per_kg = item['cost']['ddp'] / 400
        self.assertEqual(item['level']['key'], 'wholesalers' if 60 <= ddp_per_kg / 6.0 * 100 <= 100 else item['level']['key'])
        self.assertEqual(outbound['countries']['source']['name'], 'Colombia')
        self.assertEqual(outbound['countries']['target']['region'], 'Caribbean')
        self.assertEqual(outbound['comparison']['rows'], 1)
        self.assertEqual(outbound['comparison']['stale'], False)
        figures = outbound['figures']
        self.assertAlmostEqual(figures['cos'], item['cost']['ddp'])
        self.assertAlmostEqual(figures['unusedKg'], 9600)
        self.assertAlmostEqual(figures['unusedCost'], 9600 * airfare)

    def test_the_return_leg_needs_no_shipment(self):
        figures = service.route_finance(self.db, 'rt')['return']['figures']
        # full return: GSA price 1.10 x (50% of 10,000 kg) = 5,500 revenue; COS 0.40 x 5,000 = 2,000
        self.assertEqual((figures['revenue'], figures['cos'], figures['profit']), (5500.0, 2000.0, 3500.0))
        self.assertEqual(service.route_finance(self.db, 'nope'), None)

    def test_a_comparison_that_is_older_than_a_catalog_is_flagged_on_the_leg(self):
        self.db.add(models.ProductSource(id='cs', country_name='Colombia', name='Own', status='ok', product_count=1, created_at=NOW))
        self.db.add(models.PriceComparisonSnapshot(source='custom_cs', data_json='[]', fetched_at='2999-01-01T00:00:00+00:00'))
        self.db.commit()
        info = service.route_finance(self.db, 'rt')['outbound']['comparison']
        self.assertTrue(info['stale'])
        self.assertIn('after this comparison', info['stale_reasons'][0])

    def test_a_product_with_no_match_is_priced_from_the_portfolio_as_niche(self):
        route = self.db.get(models.RevenueStreamRoute, 'rt')
        route.outbound_shipment = json.dumps({'capacity_kg': 10000, 'items': [{'product_name': 'Avocado', 'kg': 100}]})
        self.db.commit()
        portfolio = [{'name': 'Avocado', 'priceUsdPerKg': 2.0, 'hsCode': '080440'}]
        with mock.patch.object(mo_engine, 'country_prices', lambda db, country: portfolio):
            item = service.route_finance(self.db, 'rt')['outbound']['shipment']['items'][0]
        self.assertEqual((item['level']['key'], item['level']['noMatch'], item['cost']['fcaPerKg']), ('niche', True, 2.0))

    def test_built_shipment_air_fares_for_market_opportunities(self):
        fares = service.built_shipment_airfares(self.db, 'Colombia', ['Jamaica', 'Bahamas'])
        self.assertEqual(list(fares), ['Jamaica'])
        self.assertEqual(fares['Jamaica']['routeName'], 'BOG → KIN')
        self.assertAlmostEqual(fares['Jamaica']['airfarePerKg'], self.airfare())
        self.assertEqual(service.built_shipment_airfares(self.db, 'Jamaica', ['Colombia']), {})

    def test_pair_pricing_gives_ddp_level_and_sell_price_for_matched_and_unmatched_products(self):
        portfolio = [{'name': 'Tomato', 'priceUsdPerKg': 1.0, 'hsCode': '070200'}, {'name': 'Avocado', 'priceUsdPerKg': 2.0, 'hsCode': '080440'}]
        with mock.patch.object(mo_engine, 'country_prices', lambda db, country: portfolio):
            result = service.pair_pricing(self.db, 'Colombia', ['Jamaica'])
        airfare = self.airfare()
        tomato = result['rows']['Jamaica|tomato']
        # DDP/kg = (1.00 + air fare) x 1.5; against the 6.00 target price; the sell price of the Wholesalers level never drops below the cost
        self.assertAlmostEqual(tomato['ddp'], (1.0 + airfare) * 1.5)
        share = tomato['ddp'] / 6.0 * 100
        self.assertEqual(tomato['level'], 'Wholesalers' if 60 <= share <= 100 else tomato['level'])
        self.assertEqual(tomato['levelNote'], f'DDP is {share:.1f}% of the target price')
        self.assertGreaterEqual(tomato['sell'], tomato['ddp'])
        # Avocado is not in the comparison: no target price, a niche market product (DDP + 20% profit); it has no tax multiplier, so no DDP yet
        avocado = result['unmatched']['Jamaica|avocado']
        self.assertEqual((avocado['ddp'], avocado['level'], avocado['sell']), (None, 'Niche Markets', None))
        self.assertNotIn('Jamaica|tomato', result['unmatched'])
        self.assertEqual(service.pair_pricing(self.db, 'Jamaica', ['Colombia']), {'airfares': {}, 'rows': {}, 'unmatched': {}})

    def test_candidates_are_the_priority_list_in_the_saved_comparison_with_market_info(self):
        self.db.add_all([models.MarketOpportunityPriority(source_country='Colombia', target_country='Jamaica', product_name=name, created_at=NOW) for name in ('Tomato', 'Avocado', 'Ghost')])
        self.db.commit()
        sam = {'products': {'070200': {'countries': {'Jamaica': {'value': 5_000_000}}}}}
        with mock.patch.object(comtrade, 'product_sam', lambda region, codes, flow, db: sam), \
                mock.patch.object(mo_engine, 'country_prices', lambda db, country: [{'name': 'Avocado', 'priceUsdPerKg': 2.0, 'hsCode': '080440'}]):
            result = service.candidates(self.db, 'Colombia', 'Jamaica', 2.0)
        self.assertEqual(result['status'], 'ready')
        by_rating = {group['rating']: group['products'] for group in result['groups']}
        tomato = by_rating['Very High'][0]
        self.assertEqual((tomato['productName'], tomato['countrySam'], tomato['hsCode']), ('Tomato', 5_000_000, '070200'))
        # DDP/kg = (1.00 + 2.00) x 1.5 = 4.50 -> 75% of the 6.00 target price: the Wholesalers range (60-100). Their sale price is 60% of 6.00 = 3.60, below the cost, so it
        # sells at cost: a 0% margin, under the 15% minimum -> the 500 kg cargo cap loses the 100 kg cap reduction.
        self.assertEqual((tomato['marketKey'], tomato['capKg'], tomato['capReduced'], tomato['marginPct']), ('wholesalers', 400, True, 0.0))
        avocado = by_rating['Unrated'][0]
        self.assertEqual((avocado['productName'], avocado['marketKey'], avocado['noMatch'], avocado['capKg']), ('Avocado', 'niche', True, 150))
        self.assertEqual(result['missingPriority'], ['Ghost'])

    def test_candidates_say_what_is_missing_first(self):
        self.assertEqual(service.candidates(self.db, 'Colombia', 'Jamaica')['status'], 'no_priority')
        self.db.add(models.MarketOpportunityPriority(source_country='Colombia', target_country='Bahamas', product_name='Tomato', created_at=NOW))
        self.db.commit()
        self.assertEqual(service.candidates(self.db, 'Colombia', 'Bahamas')['status'], 'no_comparison')


class ShipmentApiTests(unittest.TestCase):
    def setUp(self):
        database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(database)
        self.db = sessionmaker(bind=database)()
        self.addCleanup(self.db.close)
        app = FastAPI()
        app.include_router(shipments_router.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def test_allocate_endpoint_shares_the_capacity(self):
        products = [{'key': 'A|', 'marketKey': 'wholesalers', 'capKg': 300, 'countrySam': 1, 'diffPct': 10}, {'key': 'B|', 'marketKey': 'niche', 'capKg': 1000, 'countrySam': 1, 'diffPct': 20}]
        body = self.client.post('/api/shipments/allocate', json={'products': products, 'capacity_kg': 800, 'fixed_kg': {}}).json()
        self.assertEqual([(item['key'], item['kg']) for item in body['items']], [('B|', 500), ('A|', 300)])
        self.assertEqual((body['allocatedKg'], body['unallocatedKg']), (800, 0))
        manual = self.client.post('/api/shipments/allocate', json={'products': products, 'capacity_kg': 800, 'fixed_kg': {'A|': 100.9}}).json()
        self.assertTrue(next(item for item in manual['items'] if item['key'] == 'A|')['manual'])

    def test_unknown_route_is_a_404(self):
        self.assertEqual(self.client.get('/api/shipments/route-finance', params={'route_id': 'zzz'}).status_code, 404)
        self.assertEqual(self.client.get('/api/shipments/airfares', params={'source_country': 'A', 'target_countries': 'B'}).json(), {'airfares': {}})


if __name__ == '__main__':
    unittest.main()
