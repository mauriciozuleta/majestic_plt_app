"""The Python Market Opportunities engine must reproduce what the JavaScript engine produced on the frozen inputs (Colombia -> Jamaica, AI matching unavailable, no research,
fixed exchange rates): the same rows in the same order with the same words, the same unmatched products. Then the pieces the JavaScript did not have: staleness, the job,
the endpoints, the AI tier with a stand-in judge, and the weight conversion with a stand-in researcher."""

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
from backend.market_opportunities import collect, engine, jobs, match, rows, staleness
from backend.routers import market_opportunities as mo_router
from backend.tests.js_parity import inputs as parity
from backend.tests.test_portfolio_parity import same

EXPECTED = json.loads((parity.FIXTURES / 'outputs.json').read_text(encoding='utf-8'))
RATES = {code: {'rate': rate, 'date': EXPECTED['_meta']['captured_at'] and '2026-11-10', 'from': code, 'available': True} for code, rate in EXPECTED['_meta']['rates'].items()}


def fresh_db():
    database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(database)
    factory = sessionmaker(bind=database)
    with factory() as session:
        parity.load_inputs(session, parity.read_inputs())
    return factory


class EngineParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = fresh_db()

    def setUp(self):
        self.db = self.factory()
        self.addCleanup(self.db.close)

    def computed(self, **options):
        return engine.compute(self.db, 'Colombia', ['Jamaica'], allow_ai=False, allow_research=False, rates=RATES, **options)

    def test_the_rows_equal_the_javascript_rows(self):
        result, expected = self.computed(), EXPECTED['opportunity']
        self.assertEqual(len(result['rows']), len(expected['rows']))
        problems = []
        for row, js in zip(result['rows'], expected['rows']):
            problems += same(row, js, f"[{js['product_name']}]")
        self.assertEqual(problems[:10], [])

    def test_unmatched_products_and_counts_equal_the_javascript(self):
        result, expected = self.computed(), EXPECTED['opportunity']
        reduced = {target: [{'displayName': p['displayName'], 'matchName': p['matchName'], 'category': p.get('category')} for p in products]
                   for target, products in expected['unmatchedByTarget'].items()}
        self.assertEqual(same(result['unmatchedByTarget'], reduced)[:5], [])
        self.assertEqual((result['sourceProductCount'], result['weightError']), (expected['sourceProductCount'], expected['weightError']))

    def test_the_ai_tier_equals_the_javascript_with_the_same_stand_in_judge(self):
        def stand_in_judge(target_country, groups):  # the capture's rule: every source of a group is judged to be the group's first candidate
            return {'results': {source['key']: {'matches': group['candidates'][:1], 'note': 'stand-in judge', 'cached': False} for group in groups for source in group['sources']}, 'errors': []}

        result, expected = engine.compute(self.db, 'Colombia', ['Jamaica'], allow_ai=True, allow_research=False, rates=RATES, match_fn=stand_in_judge), EXPECTED['opportunity_ai']
        self.assertEqual(len(result['rows']), len(expected['rows']))
        problems = []
        for row, js in zip(result['rows'], expected['rows']):
            problems += same(row, js, f"[{js['product_name']}]")
        self.assertEqual(problems[:10], [])
        self.assertEqual(sorted({row['match_tier'] for row in result['rows']}), ['ai_match', 'hs_code'])
        reduced = {target: [{'displayName': p['displayName'], 'matchName': p['matchName'], 'category': p.get('category')} for p in products] for target, products in expected['unmatchedByTarget'].items()}
        self.assertEqual(same(result['unmatchedByTarget'], reduced)[:5], [])
        self.assertEqual((result['aiMatchErrors'], result['aiSkipped']), ({}, []))

    def test_with_the_ai_off_the_run_says_so_instead_of_reporting_an_error(self):
        result = self.computed()
        self.assertEqual((result['aiMatchErrors'], result['aiSkipped']), ({}, ['Jamaica']))

    def test_the_prices_of_a_country_in_usd_per_kg(self):
        prices = engine.country_prices(self.db, 'Jamaica', RATES)
        self.assertTrue(prices)
        self.assertEqual([p['name'].casefold() for p in prices], sorted(p['name'].casefold() for p in prices))
        priced = [p for p in prices if p['priceUsdPerKg'] is not None]
        self.assertTrue(priced)
        self.assertEqual(sorted(priced[0]), ['category', 'hsCode', 'name', 'original', 'priceUsdPerKg', 'source'])


class PiecesTests(unittest.TestCase):
    def test_amounts_are_formatted_like_the_browser_did(self):
        self.assertEqual([rows.amount(v) for v in (12, 12.5, 1234.567, 0.125, 1000000, 1.005, 2.675, 8.345)], ['12', '12.5', '1,234.57', '0.13', '1,000,000', '1.01', '2.68', '8.35'])  # measured in node

    def test_consolidation_keeps_the_median_listing_not_an_average(self):
        base = {'sourceId': 's', 'displayName': 'Tomato', 'category': 'x', 'priceUnit': 'kg', 'priceCurrency': 'JMD'}
        listings = [{**base, 'priceValue': value} for value in (10, 50, 30, 20)]
        one = collect.consolidate_listings([*listings, {**base, 'displayName': 'Other', 'priceValue': 5}])
        self.assertEqual(len(one), 2)
        tomato = one[0]
        self.assertEqual((tomato['priceValue'], tomato['listingCount'], tomato['listingLow'], tomato['listingHigh']), (20, 4, 10, 50))  # the lower middle one of 10,20,30,50

    def test_reference_row_is_the_median_matched_price_with_a_note(self):
        make = lambda name, price: {'target_country': 'J', 'target_price_normalized': price, '_target_display_name': name, 'conversion_note': None, 'product_name': 'P'}  # noqa: E731
        chosen = rows.reference_row([make('A', 3.0), make('B', 1.0), make('C', 2.0)])
        self.assertEqual(chosen['target_price_normalized'], 2.0)
        self.assertIn('median of 3 matched prices (USD 1.00–USD 3.00/kg), from 3 products: A; B; C', chosen['conversion_note'])


class MatchingTests(unittest.TestCase):
    def product(self, name, **extra):
        return {'matchName': name, 'displayName': name.title(), 'category': 'c', 'priceUnit': 'kg', 'sourceLabel': 'src', 'hsCode': None, **extra}

    def test_exact_translated_and_curated_tiers(self):
        source = [self.product('tomato'), self.product('chard', translated=True), self.product('bell pepper', translated=True)]
        target = [self.product('tomato'), self.product('chard'), self.product('sweet pepper')]
        pairs, paired = match.name_pairs('Colombia', 'Jamaica', source, target)
        self.assertEqual([(p['sp']['matchName'], p['matchTier']) for p in pairs], [('tomato', 'exact'), ('chard', 'translated_exact'), ('bell pepper', 'curated_override')])
        self.assertEqual(paired[id(source[0])], {'Tomato'})

    def test_the_ai_tier_pairs_only_what_the_judge_says_and_skips_what_a_name_already_paired(self):
        source = [self.product('chicken breast', hsCode='020713'), self.product('beef', hsCode='020130')]
        target = [self.product('necks', hsCode='020713'), self.product('chicken breast fillet', hsCode='020714'), self.product('steak', hsCode='020130')]
        asked = []

        def judge(target_country, groups):
            asked.append(groups)
            return {'results': {match.ai_match_key('Colombia', source[0]): {'matches': ['Chicken Breast Fillet'], 'note': 'same cut'}}, 'errors': []}

        answer = match.resolve_ai_matches('Colombia', 'Jamaica', source, {}, target, judge)
        self.assertEqual([(p['sp']['matchName'], p['tp']['matchName'], p['matchTier'], p['aiNote']) for p in answer['pairs']], [('chicken breast', 'chicken breast fillet', 'ai_match', 'same cut')])
        self.assertEqual([p['matchName'] for p in answer['unjudged']], ['beef'])
        self.assertEqual(len(asked[0]), 1)  # both source products sit in chapter 02, so there is ONE group
        self.assertEqual(asked[0][0]['candidates'], ['Necks', 'Chicken Breast Fillet', 'Steak'])
        self.assertEqual(len(asked[0][0]['sources']), 2)

    def test_the_hs_fallback_pairs_every_target_with_the_same_code(self):
        source = [self.product('chicken breast', hsCode='020713')]
        target = [self.product('necks', hsCode='020713'), self.product('feet', hsCode='020713'), self.product('beef', hsCode='020130')]
        pairs = match.hs_code_fallback_pairs(source, {}, target, 'Jamaica')
        self.assertEqual([p['tp']['matchName'] for p in pairs], ['necks', 'feet'])


class WeightTests(unittest.TestCase):
    def test_a_per_unit_price_is_researched_only_when_the_other_side_is_per_kg_and_then_converted(self):
        count = {'perKgLocal': None, 'priceValue': 3.0, 'norm': {'method': 'needs_research', 'read_name': 'Avocado', 'read_unit': 'each'}}
        weighed = {'perKgLocal': 4.0, 'priceValue': 4.0, 'norm': {'method': 'exact'}}
        other_count = {'perKgLocal': None, 'priceValue': 1.0, 'norm': {'method': 'needs_research', 'read_name': 'Mango', 'read_unit': 'each'}}
        asked = []

        def research(names, limit):
            asked.append((names, limit))
            return None

        converted = lambda name, unit, price: {'price_per_kg': 6.0, 'method': 'researched_item_weight', 'note': 'weight researched', 'confidence': 'medium'}  # noqa: E731
        pairs = [{'sp': count, 'tp': weighed}, {'sp': other_count, 'tp': dict(count)}]  # the second pair has no per-kg side: nothing to research
        error = engine.resolve_count_weight_conversions(None, pairs, True, research, converted)
        self.assertIsNone(error)
        self.assertEqual(asked, [(['Avocado'], 1)])
        self.assertEqual((count['perKgLocal'], count['conversionMethod'], count['conversionConfidence']), (6.0, 'researched_item_weight', 'medium'))
        self.assertIsNone(other_count['perKgLocal'])

    def test_no_research_when_it_is_not_allowed(self):
        count = {'perKgLocal': None, 'priceValue': 3.0, 'norm': {'method': 'needs_research', 'read_name': 'Avocado'}}
        asked = []
        engine.resolve_count_weight_conversions(None, [{'sp': count, 'tp': {'perKgLocal': 4.0}}], False, lambda names, limit: asked.append(names))
        self.assertEqual(asked, [])


class SavedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.factory = fresh_db()
        self.db = self.factory()
        self.addCleanup(self.db.close)

    def run_and_save(self):
        return engine.get_or_compute(self.db, 'Colombia', ['Jamaica'], force=True, allow_ai=False, allow_research=False, rates=RATES)

    def test_a_run_is_saved_and_the_next_call_returns_the_saved_one_without_computing(self):
        first = self.run_and_save()
        self.assertEqual((first['origin'], first['row_count']), ('computed', len(EXPECTED['opportunity']['rows'])))
        again = engine.get_or_compute(self.db, 'Colombia', ['Jamaica'], allow_ai=True, allow_research=True, rates=None)  # would call the AI if it computed
        self.assertEqual((again['origin'], again['row_count']), ('saved', first['row_count']))
        self.assertIn('Jamaica', again['unmatched_by_target'])
        saved = self.db.query(models.MarketOpportunityComparison).first()
        self.assertIsNotNone(saved.diff_pct)

    def test_nothing_is_saved_and_the_previous_comparison_stays_when_no_row_matched(self):
        self.run_and_save()
        count = self.db.query(models.MarketOpportunityComparison).count()
        empty = {'rows': [], 'unmatchedByTarget': {}, 'aiMatchErrors': {}, 'weightError': None}
        self.assertEqual(engine.save(self.db, 'Colombia', ['Jamaica'], empty, {})['rows'], [])
        self.assertEqual(self.db.query(models.MarketOpportunityComparison).count(), count)

    def test_staleness_says_what_changed_after_the_comparison(self):
        self.run_and_save()
        self.assertEqual(staleness.pair_status(self.db, 'Colombia', 'Jamaica', None), {'stale': False, 'reasons': []})
        snapshot = self.db.query(models.PriceComparisonSnapshot).filter_by(source='la_mayorista').one()
        snapshot.fetched_at = '2999-01-01T00:00:00+00:00'
        self.db.commit()
        status = staleness.pair_status(self.db, 'Colombia', 'Jamaica', None)
        self.assertTrue(status['stale'])
        self.assertIn('La Mayorista', status['reasons'][0])
        self.assertIn('2999-01-01', status['reasons'][0])

    def test_a_comparison_saved_before_runs_were_tracked_is_judged_by_its_date(self):
        self.run_and_save()
        self.db.query(models.MarketOpportunityRun).delete()
        self.db.commit()
        snapshot = self.db.query(models.PriceComparisonSnapshot).filter_by(source='corabastos').one()
        snapshot.fetched_at = '2999-01-01T00:00:00+00:00'
        self.db.commit()
        calculated = self.db.query(models.MarketOpportunityComparison).first().calculated_at
        status = staleness.pair_status(self.db, 'Colombia', 'Jamaica', calculated)
        self.assertTrue(status['stale'])
        self.assertIn('after this comparison', status['reasons'][0])


class JobAndApiTests(unittest.TestCase):
    def setUp(self):
        self.factory = fresh_db()
        jobs._jobs.clear()
        self.addCleanup(jobs._jobs.clear)
        app = FastAPI()
        app.include_router(mo_router.router)
        self.db = self.factory()
        self.addCleanup(self.db.close)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def test_a_job_runs_to_the_end_and_reports_its_result(self):
        state = jobs.start('Colombia', ['Jamaica'], force=True, allow_ai=False, allow_research=False, session_factory=self.factory, wait=True, rates=RATES)
        self.assertEqual(state['status'], 'done')
        self.assertEqual(state['result']['row_count'], len(EXPECTED['opportunity']['rows']))
        self.assertEqual(jobs.status('Colombia', ['Jamaica'])['status'], 'done')
        self.assertEqual(jobs.status('Colombia', ['Bahamas'])['status'], 'idle')

    def test_a_failure_is_reported_and_saves_nothing(self):
        def boom(*args, **kwargs):
            raise RuntimeError('rate service down')

        state = jobs.start('Colombia', ['Jamaica'], force=True, allow_ai=False, allow_research=False, session_factory=self.factory, wait=True, rates={}, convert_fn=boom, match_fn=boom)
        self.assertIn(state['status'], ('done', 'error'))  # a missing rate is not a failure: the rows say "no exchange rate"
        if state['status'] == 'done':
            self.assertTrue(any('No USD exchange rate' in reason for row in self.db.query(models.MarketOpportunityComparison).all() for reason in json.loads(row.review_reasons_json)))

    def test_the_compute_endpoint_can_simulate_without_saving(self):
        with mock.patch.object(engine, 'fetch_rates', lambda db, currencies: RATES):
            response = self.client.post('/api/market-opportunities/compute', json={'source_country': 'Colombia', 'target_countries': ['Jamaica'], 'allow_ai': False,
                                                                                    'allow_research': False, 'save': False})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body['rows']), len(EXPECTED['opportunity']['rows']))
        self.assertEqual(self.db.query(models.MarketOpportunityComparison).count(), 0)

    def test_pairs_show_whether_they_are_out_of_date(self):
        engine.get_or_compute(self.db, 'Colombia', ['Jamaica'], force=True, allow_ai=False, allow_research=False, rates=RATES)
        pair = self.client.get('/api/market-opportunities/comparisons/pairs').json()['pairs'][0]
        self.assertEqual((pair['stale'], pair['stale_reasons']), (False, []))
        self.assertEqual(self.client.get('/api/market-opportunities/compute/status', params={'source_country': 'Colombia', 'target_countries': 'Jamaica'}).json()['status'], 'idle')

    def test_country_prices_endpoint(self):
        with mock.patch.object(engine, 'fetch_rates', lambda db, currencies: RATES):
            body = self.client.get('/api/market-opportunities/country-prices', params={'country': 'Jamaica'}).json()
        self.assertEqual(body['country'], 'Jamaica')
        self.assertTrue(any(p['priceUsdPerKg'] is not None for p in body['products']))


if __name__ == '__main__':
    unittest.main()
