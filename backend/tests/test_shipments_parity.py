"""The Python shipment functions must give what the ORIGINAL JavaScript gave for the same inputs (backend/tests/js_parity/shipment_scenarios.py; the answers were captured from the
JavaScript before it moved): market level, suggested sale price, candidate market info, candidate grouping, the allocation of kilos (38 cases incl. manual weights and short
capacity), the cost chain and totals, route metrics, the air fare per kg of a leg, and the revenue / COS / profit of both legs."""

import json
import unittest

from backend.shipments import allocation, finance, market
from backend.tests.js_parity import inputs as parity
from backend.tests.test_portfolio_parity import same

EXPECTED = json.loads((parity.FIXTURES / 'outputs.json').read_text(encoding='utf-8'))
SCENARIOS, ANSWERS = EXPECTED['shipment_scenarios'], EXPECTED['shipments']


class ShipmentParityTests(unittest.TestCase):
    def check(self, name, compute):
        cases, answers = SCENARIOS[name], ANSWERS[name]
        self.assertEqual(len(cases), len(answers), name)
        problems = []
        for index, (case, answer) in enumerate(zip(cases, answers)):
            problems += same(compute(case), answer, f'{name}[{index}]')
        self.assertEqual(problems[:8], [], name)

    def test_market_level(self):
        self.check('market_level', lambda c: market.market_level_for(c['ddp'], c['target'], c['markets']))

    def test_suggested_sell_price(self):
        self.check('sell_price', lambda c: market.suggested_sell_price(c['key'], c['ddp'], c['target'], c['markets']))

    def test_candidate_market_info(self):
        self.check('product_info', lambda c: allocation.product_market_info(c['row'], c['params']['airfarePerKg'], c['params']['multiplier'], c['params']['destinationMarkets'], c['params']['countrySam']))

    def test_candidate_grouping(self):
        self.check('group', lambda c: allocation.group_products_by_rating(c['rows'], lambda row: c['sam'].get(row.get('hs_code')), c['ratings']))

    def test_allocation_of_kilos(self):
        self.check('allocate', lambda c: allocation.allocate_shipment(c['products'], c['capacity'], dict(c['fixed'])))

    def test_cost_chain_and_totals(self):
        self.check('finance', lambda c: finance.finance_for_shipment(c['shipment'], c['prices'], c['multipliers'], c['airfare'], c['markets']))

    def test_route_metrics(self):
        self.check('block_hours', finance.block_hours_for)
        self.check('distance', lambda c: finance.distance_nm(*c))
        self.check('metrics', lambda c: finance.compute_route_metrics(c['origin'], c['destination'], c['aircraft'], c['provider']))

    def test_air_fare_per_kg_of_a_leg(self):
        self.check('leg_price', lambda c: finance.leg_price_per_kg(c['route'], c['leg'], c['context']['origin'], c['context']['destination'], c['context']['returnBranch'],
                                                                   c['context']['aircraft'], c['context']['provider']))

    def test_return_leg_revenue_cos_profit(self):
        self.check('return_leg', lambda c: finance.return_leg_finance(c['route'], c['context']['origin'], c['context']['destination'], c['context']['returnBranch'],
                                                                      c['context']['aircraft'], c['context']['provider']))

    def test_outbound_leg_revenue_cos_profit(self):
        def compute(case):
            base = SCENARIOS['finance'][case['finance_case']]
            result = finance.finance_for_shipment(base['shipment'], base['prices'], base['multipliers'], base['airfare'], base['markets'])
            return finance.outbound_leg_finance(base['shipment'], result, base['airfare'], case['aircraft'])

        self.check('outbound_leg', compute)

    def test_the_scenarios_really_exercise_the_branches(self):
        """Guards against a fixture that proves nothing: the grids must contain a capped wholesaler, a reduced cap, a manual weight and a missing figure."""
        allocated = [allocation.allocate_shipment(c['products'], c['capacity'], dict(c['fixed'])) for c in SCENARIOS['allocate']]
        self.assertTrue(any(item.get('manual') for result in allocated for item in result['items']))
        self.assertTrue(any(result['unallocatedKg'] > 0 for result in allocated))
        infos = [allocation.product_market_info(c['row'], c['params']['airfarePerKg'], c['params']['multiplier'], c['params']['destinationMarkets'], c['params']['countrySam']) for c in SCENARIOS['product_info']]
        self.assertTrue(any(info['capReduced'] for info in infos))
        self.assertTrue(any(info['marketKey'] is None for info in infos))
        legs = [finance.leg_price_per_kg(c['route'], c['leg'], c['context']['origin'], c['context']['destination'], c['context']['returnBranch'], c['context']['aircraft'], c['context']['provider'])
                for c in SCENARIOS['leg_price']]
        self.assertTrue(any(leg['value'] is not None for leg in legs) and any(leg['value'] is None for leg in legs))


if __name__ == '__main__':
    unittest.main()
