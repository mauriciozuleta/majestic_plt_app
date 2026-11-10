import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, snapshot_store
from backend.catalog_normalization import catalog, hs, hs_store
from backend.comtrade import classification, product_classification
from backend.data_history import service as history_service
from backend.data_history import store as history_store
from backend.database import Base, get_db
from backend.routers import hs_codes as hs_router
from backend.routers import product_sources

# a small stand-in for Comtrade's reference: 0702 has a single subheading (0702.00); 0201 has three; 0804 two; chapter 24 is outside food
REFERENCE = {
    '07': 'Edible vegetables', '0702': 'Tomatoes, fresh or chilled', '070200': 'Tomatoes, fresh or chilled',
    '02': 'Meat', '0201': 'Meat of bovine animals, fresh or chilled', '020110': 'Carcasses and half-carcasses', '020120': 'Other cuts with bone in', '020130': 'Boneless',
    '08': 'Fruit', '0804': 'Dates, figs, pineapples, avocados, guavas, mangoes', '080430': 'Pineapples', '080440': 'Avocados',
    '03': 'Fish', '0302': 'Fish, fresh or chilled', '030211': 'Trout',
    '24': 'Tobacco', '2401': 'Unmanufactured tobacco', '240110': 'Tobacco, not stemmed',
}


class HsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(history_store.use_database, history_store.database_path())
        history_store.use_database(Path(self.tmp.name) / 'history.db')
        for patch in (mock.patch.object(classification, '_load_reference', lambda: REFERENCE), mock.patch.object(product_classification, '_headings_cache', None)):
            patch.start()
            self.addCleanup(patch.stop)
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        for name, code in (('Jamaica', 'JM'), ('Colombia', 'CO'), ('United States', 'US')):
            self.db.add(models.CountryReferenceCatalog(id=code, name=name, country_code=code, currency='x', currency_code='XXX', region='r'))
        self.db.add(models.ProductSource(id='j1', country_name='Jamaica', name='MOA', status='ok', product_count=3, created_at='2026-01-01'))
        self.db.commit()

    def add_catalog(self, source, products):
        self.db.add(models.PriceComparisonSnapshot(source=source, data_json=json.dumps(products), fetched_at='2026-11-10'))
        self.db.commit()

    def jamaica_products(self):
        return [
            {'id': 'a', 'category': 'Vegetables', 'name': 'Tomato', 'unit': 'kg', 'price': 3.0, 'currency': 'JMD'},
            {'id': 'b', 'category': 'Beef', 'name': 'Beef Primal Chuck', 'unit': 'kg', 'price': 9.0, 'currency': 'JMD'},
            {'id': 'c', 'category': 'Fruit', 'name': 'Mystery fruit', 'unit': 'kg', 'price': 2.0, 'currency': 'JMD'},
        ]


class ParseCodeTests(HsTestCase):
    def test_a_heading_with_one_subheading_is_a_real_six_digit_code(self):
        code = hs.parse_code('0702')
        self.assertEqual((code.hs6, code.level), ('070200', 6))

    def test_a_heading_without_a_single_subheading_is_padded_and_level_four(self):
        for raw in ('0201', '020100', '0201.00'):
            code = hs.parse_code(raw)
            self.assertEqual((code.hs6, code.level), ('020100', 4), raw)

    def test_six_digits_and_punctuation_and_a_country_prefix(self):
        self.assertEqual(hs.parse_code('0201.10').hs6, '020110')
        self.assertEqual(hs.parse_code('JM070200').hs6, '070200')

    def test_unknown_or_too_coarse_codes_are_refused_with_a_reason(self):
        for raw in ('9999', '02', '123456', '', None, '020199'):
            with self.assertRaises(hs.HsError, msg=str(raw)):
                hs.parse_code(raw)


class LookupTests(HsTestCase):
    def test_assignment_wins_then_the_name_only_cache_then_no_code(self):
        self.db.add(models.ProductHsAssignment(country='Jamaica', product_key='tomato', hs_code='070200', hs_level=6, status='confirmed', method='manual'))
        self.db.add(models.ProductHsCode(product_key='beef primal chuck', hs_code='020130', description='x'))
        self.db.commit()
        index = hs.build_index(self.db)
        tomato = index.block('Jamaica', 'Tomato')
        self.assertEqual((tomato['code'], tomato['label'], tomato['status'], tomato['source']), ('JM070200', 'ok', 'confirmed', 'assignment'))
        beef = index.block('Jamaica', 'Beef Primal Chuck')
        self.assertEqual((beef['code'], beef['status'], beef['source'], beef['ai_suggested']), ('JM020130', 'suggested', 'legacy', True))
        none = index.block('Jamaica', 'Mystery fruit')
        self.assertEqual((none['code'], none['hs6'], none['label']), (None, None, 'no_code'))

    def test_the_same_name_can_carry_a_different_code_in_each_country(self):
        self.db.add_all([models.ProductHsAssignment(country='Jamaica', product_key='avocado', hs_code='080440', hs_level=6, status='confirmed'),
                         models.ProductHsAssignment(country='Colombia', product_key='avocado', hs_code='080430', hs_level=6, status='confirmed')])
        self.db.commit()
        index = hs.build_index(self.db)
        self.assertEqual((index.block('Jamaica', 'Avocado')['code'], index.block('Colombia', 'Avocado')['code']), ('JM080440', 'CO080430'))

    def test_a_padded_heading_is_labelled_heading_only(self):
        self.db.add(models.ProductHsAssignment(country='Jamaica', product_key='beef', hs_code='020100', hs_level=4, status='confirmed'))
        self.db.commit()
        block = hs.build_index(self.db).block('Jamaica', 'Beef')
        self.assertEqual((block['code'], block['level'], block['label']), ('JM020100', 4, 'heading_only'))

    def test_the_catalog_gets_an_hs_block_per_product_and_never_a_placeholder(self):
        self.add_catalog('custom_j1', self.jamaica_products())
        self.db.add(models.ProductHsAssignment(country='Jamaica', product_key='tomato', hs_code='070200', hs_level=6, status='confirmed'))
        self.db.commit()
        products = json.loads(self.db.query(models.PriceComparisonSnapshot).one().data_json)
        catalog.annotate_with_db(self.db, 'custom_j1', products)
        by_name = {p['name']: p['hs'] for p in products}
        self.assertEqual(by_name['Tomato']['code'], 'JM070200')
        self.assertIsNone(by_name['Mystery fruit']['code'])
        self.assertEqual(by_name['Mystery fruit']['label'], 'no_code')

    def test_colombian_products_are_coded_under_their_english_name_in_colombia(self):
        self.db.add(models.ProductHsAssignment(country='Colombia', product_key='tomato', hs_code='070200', hs_level=6, status='confirmed'))
        self.db.commit()
        with mock.patch.object(catalog, 'translate_name', lambda name, overrides=None: mock.Mock(text='Tomato', translated=True, tier='dictionary')):
            rows = catalog.annotate_with_db(self.db, 'la_mayorista', [{'id': 't', 'nameEs': 'Tomate', 'unit': 'kg', 'price': 1000, 'category': 'hortalizas'}])
        self.assertEqual(rows[0]['hs']['code'], 'CO070200')


class CheckTests(HsTestCase):
    def test_messages_for_the_cases_a_person_must_look_at(self):
        self.assertEqual(hs.check('Jamaica', 'Tomato', 'Vegetables', '070200')['status'], 'ok')
        self.assertEqual(hs.check('Jamaica', 'x', None, '9999')['status'], 'error')
        padded = hs.check('Jamaica', 'Beef', 'Beef', '0201')
        self.assertEqual((padded['status'], padded['level'], padded['hs6']), ('warning', 4, '020100'))
        self.assertIn('heading only', padded['messages'][0])
        wrong_chapter = hs.check('Jamaica', 'Beef Chuck', 'Beef', '030211')
        self.assertEqual(wrong_chapter['status'], 'warning')
        self.assertIn('chapter', wrong_chapter['messages'][0])
        self.assertEqual(hs.check('Jamaica', 'Leaf', 'Fruit', '240110')['status'], 'warning')

    def test_the_same_product_under_a_different_heading_in_another_country_is_flagged(self):
        self.db.add(models.ProductHsAssignment(country='Colombia', product_key='avocado', hs_code='080430', hs_level=6, status='confirmed'))
        self.db.commit()
        verdict = hs.check('Jamaica', 'Avocado', 'Fruit', '020130', hs.build_index(self.db))
        self.assertTrue(any('Colombia' in message for message in verdict['messages']))


class SuggestTests(HsTestCase):
    def test_a_peer_suggestion_prefers_what_a_person_confirmed_and_says_where_it_came_from(self):
        self.db.add_all([models.ProductHsAssignment(country='Colombia', product_key='avocado', hs_code='080440', hs_level=6, status='confirmed'),
                         models.ProductHsAssignment(country='United States', product_key='avocado', hs_code='080430', hs_level=6, status='suggested')])
        self.db.commit()
        out = hs.suggest(self.db, [{'country': 'Jamaica', 'name': 'Avocado', 'category': 'Fruit'}])
        suggestion = out['results'][0]['suggestion']
        self.assertEqual((suggestion['code'], suggestion['method']), ('080440', 'peer'))
        self.assertIn('Colombia', suggestion['note'])
        self.assertEqual(out['results'][0]['validation']['status'], 'ok')

    def test_a_curated_rule_comes_first(self):
        rules = Path(self.tmp.name) / 'rules.json'
        rules.write_text(json.dumps({'rules': {'Tomato': '0702'}}), encoding='utf-8')
        with mock.patch.object(hs, 'RULES_FILE', rules):
            out = hs.suggest(self.db, [{'country': 'Jamaica', 'name': 'tomato'}])
        self.assertEqual((out['results'][0]['suggestion']['method'], out['results'][0]['tried'][0]), ('rule', 'rule'))

    def test_claude_is_only_asked_when_allowed_and_a_failure_is_reported_not_hidden(self):
        with mock.patch.object(hs, 'suggest_with_claude', side_effect=RuntimeError('Claude API error 400: credit balance is too low')) as claude:
            quiet = hs.suggest(self.db, [{'country': 'Jamaica', 'name': 'Mystery fruit'}])
            claude.assert_not_called()
            loud = hs.suggest(self.db, [{'country': 'Jamaica', 'name': 'Mystery fruit'}], allow_ai=True)
        self.assertEqual((quiet['errors'], quiet['results'][0]['suggestion']), ([], None))
        self.assertIn('credit balance', loud['errors'][0])

    def test_a_model_suggestion_the_reference_does_not_know_is_dropped(self):
        answers = [{'code': '999999', 'method': 'ai', 'confidence': 'medium', 'note': ''}, {'code': '080440', 'method': 'ai', 'confidence': 'medium', 'note': ''}]
        with mock.patch.object(hs, 'suggest_with_claude', return_value=answers):
            out = hs.suggest(self.db, [{'country': 'Jamaica', 'name': 'A'}, {'country': 'Jamaica', 'name': 'B'}], allow_ai=True)
        self.assertEqual([row['suggestion'] and row['suggestion']['code'] for row in out['results']], [None, '080440'])

    def test_the_local_model_can_only_answer_with_a_code_it_was_shown(self):
        replies = iter(['0804', '080440', '0804', 'I think 111111'])

        def fake_chat(model, messages, cancel, options=None, think=False):
            yield next(replies)

        with mock.patch('backend.local_models.ollama_client.stream_chat', fake_chat):
            found = hs.suggest_with_local_model([{'name': 'Avocado', 'country': 'Jamaica', 'category': 'Fruit'}, {'name': 'Pineapple', 'country': 'Jamaica'}], 'qwen')
        self.assertEqual(found[0]['code'], '080440')
        self.assertEqual(found[1]['code'], '0804')  # an answer outside the shown subheadings falls back to the heading


class SaveTests(HsTestCase):
    def setUp(self):
        super().setUp()
        self.add_catalog('custom_j1', self.jamaica_products())

    def stored(self):
        return {p['name']: p['hs'] for p in json.loads(self.db.query(models.PriceComparisonSnapshot).filter_by(source='custom_j1').one().data_json)}

    def test_saving_confirms_the_code_updates_every_catalog_and_records_the_history(self):
        result = hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '0702', 'category': 'Vegetables'}], 'tester')
        self.assertEqual((result['saved'], result['refused']), (1, []))
        row = self.db.get(models.ProductHsAssignment, ('Jamaica', 'tomato'))
        self.assertEqual((row.hs_code, row.status, row.assigned_by), ('070200', 'confirmed', 'tester'))
        self.assertEqual(self.stored()['Tomato']['code'], 'JM070200')
        self.assertEqual(history_store.latest('hs:assignments')['version'], 1)
        self.assertIsNotNone(history_store.latest('snapshot:custom_j1'))

    def test_changing_a_code_makes_it_corrected_and_an_unknown_code_is_refused(self):
        hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '070200'}])
        out = hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '080440'}, {'country': 'Jamaica', 'name': 'Mystery fruit', 'code': '1234'}])
        self.assertEqual(out['saved'], 1)
        self.assertEqual(out['refused'][0]['name'], 'Mystery fruit')
        self.assertEqual(self.db.get(models.ProductHsAssignment, ('Jamaica', 'tomato')).status, 'corrected')

    def test_replacing_an_older_name_only_code_counts_as_a_correction(self):
        self.db.add(models.ProductHsCode(product_key='tomato', hs_code='080440'))
        self.db.commit()
        hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '070200'}])
        self.assertEqual(self.db.get(models.ProductHsAssignment, ('Jamaica', 'tomato')).status, 'corrected')

    def test_status_and_the_review_queue_order(self):
        hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '070200'}, {'country': 'Jamaica', 'name': 'Beef Primal Chuck', 'code': '0201'}])
        self.db.add(models.ProductHsCode(product_key='mystery fruit', hs_code='080440'))
        self.db.commit()
        hs_store.reannotate_catalogs(self.db, 'test')
        counts = hs_store.status(self.db)['countries']['Jamaica']
        self.assertEqual(counts, {'confirmed': 1, 'heading_only': 1, 'suggested': 1})
        queue = hs_store.queue(self.db, 'Jamaica')
        self.assertEqual([(item['name'], item['reason']) for item in queue['items']], [('Beef Primal Chuck', 'heading_only'), ('Mystery fruit', 'unreviewed')])
        self.assertEqual(hs_store.queue(self.db, 'Jamaica', include_confirmed=True)['total'], 3)

    def test_the_queue_puts_products_in_a_saved_comparison_first(self):
        self.db.add(models.MarketOpportunityComparison(id='c1', product_name='Mystery fruit', source_country='Jamaica', target_country='Colombia', calculated_at='2026-11-10'))
        self.db.commit()
        hs_store.reannotate_catalogs(self.db, 'test')
        names = [item['name'] for item in hs_store.queue(self.db, 'Jamaica')['items']]
        self.assertEqual(names[0], 'Mystery fruit')

    def test_the_assignments_can_be_restored_from_the_history(self):
        hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '070200'}])
        hs_store.save_assignments(self.db, [{'country': 'Jamaica', 'name': 'Tomato', 'code': '080440'}])
        history_service.restore(self.db, 'hs:assignments', 1)
        self.assertEqual(self.db.get(models.ProductHsAssignment, ('Jamaica', 'tomato')).hs_code, '070200')
        self.assertEqual(self.stored()['Tomato']['code'], 'JM070200')

    def test_storing_a_source_no_longer_starts_a_classification(self):
        self.assertFalse(hasattr(product_sources, 'classify_source_products_in_background'))
        source = self.db.get(models.ProductSource, 'j1')
        with mock.patch('threading.Thread') as thread:
            product_sources._store(self.db, source, self.jamaica_products(), 'file', 'loaded')
        thread.assert_not_called()
        self.assertEqual(self.stored()['Mystery fruit']['label'], 'no_code')


class ApiTests(HsTestCase):
    def setUp(self):
        super().setUp()
        self.add_catalog('custom_j1', self.jamaica_products())
        snapshot_store.record_current(self.db, 'custom_j1', 'x')
        app = FastAPI()
        app.include_router(hs_router.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def test_validate_suggest_save_status_queue_lookup(self):
        item = {'country': 'Jamaica', 'name': 'Tomato', 'category': 'Vegetables', 'code': '0702'}
        self.assertEqual(self.client.post('/api/hs-codes/validate', json=[item]).json()['results'][0]['hs6'], '070200')
        self.assertEqual(self.client.post('/api/hs-codes/suggest', json={'items': []}).status_code, 400)
        many = [{'country': 'Jamaica', 'name': f'p{i}'} for i in range(13)]
        self.assertEqual(self.client.post('/api/hs-codes/suggest', json={'items': many, 'allow_ai': True}).status_code, 400)
        saved = self.client.post('/api/hs-codes/save', json={'items': [item, {**item, 'name': 'Bad', 'code': '1'}], 'saved_by': 'M. Zuleta'}).json()
        self.assertEqual((saved['saved'], len(saved['refused'])), (1, 1))
        self.assertEqual(self.client.get('/api/hs-codes/lookup', params={'country': 'Jamaica', 'name': 'Tomato'}).json()['code'], 'JM070200')
        self.assertEqual(self.client.get('/api/hs-codes/status').json()['countries']['Jamaica']['confirmed'], 1)
        self.assertEqual(self.client.get('/api/hs-codes/queue', params={'country': 'Jamaica'}).json()['total'], 2)


if __name__ == '__main__':
    unittest.main()
