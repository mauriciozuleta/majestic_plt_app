import json
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.catalog_normalization.catalog import annotate
from backend.catalog_normalization.store import ItemWeight, MemoryStore
from backend.catalog_normalization.validation import validate_weight
from backend.database import Base, get_db
from backend.routers import catalog_normalization as router_module


class ValidationTests(unittest.TestCase):
    def test_a_sensible_weight_is_ok_and_previews_the_price_per_kg(self):
        result = validate_weight('Lulo', 'each', 0.09, examples=[{'label': 'Lulo', 'price': 0.9, 'unit_text': 'each'}])
        self.assertEqual(result.status, 'ok')
        self.assertAlmostEqual(result.previews[0]['price_per_kg'], 10.0)

    def test_zero_and_implausible_weights_are_errors(self):
        self.assertEqual(validate_weight('Lulo', 'each', 0).status, 'error')
        self.assertEqual(validate_weight('Lulo', 'each', None).status, 'error')
        self.assertEqual(validate_weight('Lulo', 'each', 90.0).status, 'error')  # 90 kg for one item
        self.assertEqual(validate_weight('Cilantro', 'bunch', 8.0).status, 'error')  # an 8 kg bunch

    def test_a_weight_far_from_usda_is_a_warning(self):
        result = validate_weight('Pineapples', 'each', 0.2)  # USDA: about 1,775 g
        self.assertEqual(result.status, 'warning')
        self.assertTrue(any('USDA' in message for message in result.messages))
        self.assertEqual(validate_weight('Pineapples', 'each', 1.5).status, 'ok')

    def test_the_price_per_kg_is_checked_against_the_same_products_other_listings(self):
        examples = [{'label': 'Cilantro', 'price': 9000.0, 'unit_text': 'per bunch', 'source': 'corabastos'}]
        peers = [{'source': 'corabastos', 'per_kg': 3000.0}]
        self.assertEqual(validate_weight('Cilantro', 'bunch', 0.15, examples=examples, peers=peers).status, 'warning')  # 60,000/kg against 3,000/kg
        self.assertEqual(validate_weight('Cilantro', 'bunch', 3.0, examples=examples, peers=peers).status, 'ok')

    def test_two_sources_in_the_same_currency_are_compared_with_each_other(self):
        examples = [{'label': 'Cilantro', 'price': 9000.0, 'unit_text': 'per bunch', 'source': 'corabastos', 'group': 'COP'}]
        peers = [{'source': 'la_mayorista', 'group': 'COP', 'per_kg': 3000.0}]  # La Mayorista lists cilantro per kg
        self.assertEqual(validate_weight('Cilantro', 'bunch', 0.085, examples=examples, peers=peers).status, 'warning')  # 105,882/kg against 3,000/kg

    def test_prices_of_two_sources_are_never_mixed(self):
        examples = [{'label': 'Cilantro', 'price': 9000.0, 'unit_text': 'per bunch', 'source': 'corabastos'}, {'label': 'Cilantro', 'price': 0.74, 'unit_text': 'per bunch', 'source': 'usa_retail_produce'}]
        peers = [{'source': 'corabastos', 'per_kg': 60000.0}, {'source': 'usa_retail_produce', 'per_kg': 8.0}]
        result = validate_weight('Cilantro', 'bunch', 0.15, examples=examples, peers=peers)  # 60,000 COP/kg and 4.93 USD/kg: each close to its own peers
        self.assertEqual(result.status, 'ok')
        self.assertEqual({p['source'] for p in result.previews}, {'corabastos', 'usa_retail_produce'})

    def test_a_range_that_does_not_hold_the_weight_is_flagged(self):
        self.assertEqual(validate_weight('Lulo', 'each', 0.09, min_kg=0.1, max_kg=0.2).status, 'warning')
        self.assertEqual(validate_weight('Lulo', 'each', 0.09, min_kg=0.3, max_kg=0.2).status, 'error')


class EndpointTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        products = [{'category': 'Retail Produce', 'product_en': 'Rhubarb', 'commodity': 'Rhubarb', 'price': 0.74, 'unit': 'USD/per bunch', 'detail': True, 'source_date': 'Nov 6'},
                    {'category': 'Retail Produce', 'product_en': 'Lulo', 'commodity': 'Lulo', 'price': 0.9, 'unit': 'USD/each', 'detail': True, 'source_date': 'Nov 6'},
                    {'category': 'Retail Produce', 'product_en': 'Apples', 'commodity': 'Apples', 'price': 3.0, 'unit': 'USD/3 lb bag', 'detail': True, 'source_date': 'Nov 6'}]
        annotate('usa_retail_produce', products, MemoryStore())
        with self.Session() as db:
            db.add(models.PriceComparisonSnapshot(source='usa_retail_produce', data_json=json.dumps(products), fetched_at='2026-11-09'))
            db.commit()
        app = FastAPI()
        app.include_router(router_module.router)

        def override():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def test_the_summary_and_the_form_list_the_products_that_need_a_weight(self):
        self.assertEqual(self.client.get('/api/catalog-normalization/missing-summary').json()['countries'], {'United States': 2})
        items = self.client.get('/api/catalog-normalization/missing', params={'country': 'United States'}).json()['items']
        self.assertEqual(sorted(item['name'] for item in items), ['Lulo', 'Rhubarb'])
        self.assertEqual(self.client.get('/api/catalog-normalization/missing', params={'country': 'Colombia'}).json()['items'], [])

    def test_validate(self):
        body = {'items': [{'name': 'Lulo', 'count_unit': 'each', 'weight_g': 90}, {'name': 'Lulo', 'count_unit': 'each', 'weight_g': 90000}]}
        results = self.client.post('/api/catalog-normalization/validate', json=body).json()['results']
        self.assertEqual([r['status'] for r in results], ['ok', 'error'])
        self.assertAlmostEqual(results[0]['previews'][0]['price_per_kg'], 10.0)

    def test_the_ai_search_returns_validated_values_and_saves_nothing(self):
        found = [ItemWeight('Lulo', 'each', 0.09, 0.07, 0.12, confidence='medium', note='a Colombian lulo', sources=['https://example.org'])]
        with mock.patch.object(router_module, 'research_item_weights', return_value=found):
            results = self.client.post('/api/catalog-normalization/suggest', json={'items': [{'name': 'Lulo', 'count_unit': 'each'}], 'confirm_usd': 0.09}).json()['results']
        self.assertAlmostEqual(results[0]['weight_g'], 90.0)
        self.assertEqual(results[0]['validation']['status'], 'ok')
        with self.Session() as db:
            self.assertEqual(db.query(models.CatalogItemWeight).count(), 0)

    def test_the_ai_search_reports_why_it_failed(self):
        with mock.patch.object(router_module, 'research_item_weights', side_effect=RuntimeError('Your credit balance is too low')):
            response = self.client.post('/api/catalog-normalization/suggest', json={'items': [{'name': 'Lulo', 'count_unit': 'each'}], 'confirm_usd': 0.09})
        self.assertEqual(response.status_code, 502)
        self.assertIn('credit balance', response.json()['detail'])

    # ---------------------------------------------------------------- the cost guard: a paid web search never starts by itself (one click once cost about 8 USD)
    def test_the_ai_search_is_refused_without_a_confirmed_amount_and_costs_nothing(self):
        with mock.patch.object(router_module, 'research_item_weights') as paid:
            for body in ({'items': [{'name': 'Lulo', 'count_unit': 'each'}]}, {'items': [{'name': 'Lulo', 'count_unit': 'each'}], 'confirm_usd': 0.01}):
                response = self.client.post('/api/catalog-normalization/suggest', json=body)
                self.assertEqual(response.status_code, 409)
                self.assertIn('needs_confirmation', response.json()['detail'])
                self.assertIn('$0.09', response.json()['detail'])
            paid.assert_not_called()

    def test_the_research_job_gives_an_estimate_and_starts_only_with_a_confirmed_amount_and_is_capped(self):
        with mock.patch.object(router_module, '_run_research') as job:
            dry = self.client.post('/api/catalog-normalization/research', json={'dry_run': True}).json()
            self.assertEqual(dry['status'], 'dry_run')
            self.assertEqual(dry['estimated_usd'], round(dry['would_research'] * dry['usd_per_product'], 2))
            self.assertLessEqual(dry['would_research'], dry['max_per_run'])
            refused = self.client.post('/api/catalog-normalization/research', json={}).json()
            self.assertEqual(refused['status'], 'needs_confirmation')
            too_little = self.client.post('/api/catalog-normalization/research', json={'confirm_usd': 0.0}).json()
            self.assertEqual(too_little['status'], 'needs_confirmation')
            job.assert_not_called()  # nothing was started, nothing spent
            started = self.client.post('/api/catalog-normalization/research', json={'confirm_usd': dry['estimated_usd']}).json()
            self.assertEqual(started['status'], 'started')
            job.assert_called_once()

    def test_one_run_never_researches_more_than_the_cap(self):
        from backend.catalog_normalization import researcher

        self.assertEqual(researcher.estimated_usd(98), 8.82)  # the run that cost about 8 USD
        with mock.patch.object(router_module, '_needs', return_value=[{'product': f'p{i}', 'count_unit': 'each', 'sources': [], 'countries': [], 'examples': [], 'rows': 1} for i in range(200)]):
            dry = self.client.post('/api/catalog-normalization/research', json={'dry_run': True, 'limit': 500}).json()
        self.assertEqual((dry['pending'], dry['would_research']), (200, researcher.MAX_PRODUCTS_PER_RUN))

    def test_save_stores_the_weight_converts_the_catalog_and_updates_the_count(self):
        body = {'items': [{'name': 'Lulo', 'count_unit': 'each', 'weight_g': 90, 'origin': 'manual'},
                          {'name': 'Rhubarb', 'count_unit': 'bunch', 'weight_g': 90000, 'origin': 'manual'}]}
        result = self.client.post('/api/catalog-normalization/weights', json=body).json()
        self.assertEqual(result['saved'], 1)
        self.assertEqual([item['name'] for item in result['refused']], ['Rhubarb'])  # an implausible value is refused
        self.assertEqual(result['still_missing'], 1)
        self.assertEqual(self.client.get('/api/catalog-normalization/missing-summary').json()['countries'], {'United States': 1})
        with self.Session() as db:
            saved = db.query(models.CatalogItemWeight).one()
            self.assertEqual((saved.confidence, saved.item_kg), ('user', 0.09))
            products = json.loads(db.query(models.PriceComparisonSnapshot).one().data_json)
            lulo = next(p for p in products if p.get('detail') and p['commodity'] == 'Lulo')
            self.assertAlmostEqual(lulo['norm']['price_per_kg'], 10.0)
            self.assertEqual(lulo['norm']['confidence'], 'user')


if __name__ == '__main__':
    unittest.main()
