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

from backend import models
from backend.catalog_normalization import catalog
from backend.country_profile import access_pack, claude_client
from backend.data_history import service as history_service
from backend.data_history import store as history_store
from backend.database import Base, get_db
from backend.routers import competitiveness
from backend.tests.test_hs_codes import REFERENCE
from backend.comtrade import classification


class AccessBriefTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(history_store.use_database, history_store.database_path())
        history_store.use_database(Path(self.tmp.name) / 'history.db')
        patch = mock.patch.object(classification, '_load_reference', lambda: REFERENCE)
        patch.start()
        self.addCleanup(patch.stop)
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        for name, code in (('Jamaica', 'JM'), ('Colombia', 'CO')):
            self.db.add(models.CountryReferenceCatalog(id=code, name=name, country_code=code, currency='x', currency_code='XXX', region='r'))
        self.db.add(models.ProductSource(id='c1', country_name='Colombia', name='Own source', status='ok', product_count=4, created_at='2026-01-01'))
        self.db.add_all([
            models.ProductHsAssignment(country='Colombia', product_key='tomato', hs_code='070200', hs_level=6, status='confirmed'),
            models.ProductHsAssignment(country='Colombia', product_key='cherry tomato', hs_code='070200', hs_level=6, status='suggested'),
            models.ProductHsAssignment(country='Colombia', product_key='beef', hs_code='020100', hs_level=4, status='confirmed'),
        ])
        products = [{'id': str(i), 'category': 'x', 'name': name, 'unit': 'kg', 'price': 1.0, 'currency': 'COP'} for i, name in enumerate(['Tomato', 'Cherry Tomato', 'Beef', 'Mystery'])]
        self.db.add(models.PriceComparisonSnapshot(source='custom_c1', data_json=json.dumps(products), fetched_at='2026-11-09T10:00:00+00:00'))
        self.db.commit()
        rows = self.db.query(models.PriceComparisonSnapshot).all()
        for row in rows:
            data = json.loads(row.data_json)
            catalog.annotate_with_db(self.db, row.source, data)
            row.data_json = json.dumps(data)
        self.db.commit()


class PackTests(AccessBriefTestCase):
    def test_the_portfolio_is_grouped_by_hs_heading_and_flags_what_is_not_solid(self):
        pack = access_pack.portfolio_by_heading(self.db, 'Colombia')
        by_heading = {entry['heading']: entry for entry in pack['headings']}
        self.assertEqual(pack['product_count'], 4)
        self.assertEqual(by_heading['0702']['count'], 2)
        self.assertEqual(by_heading['0702']['codes'], ['CO070200'])
        self.assertEqual(by_heading['0702']['unreviewed'], 1)
        self.assertEqual(by_heading['0201']['heading_only'], 1)
        self.assertEqual(pack['no_code'], {'count': 1, 'names': ['Mystery']})
        self.assertEqual(access_pack.portfolio_by_heading(self.db, 'Jamaica')['product_count'], 0)

    def test_the_text_for_the_model_lists_headings_gaps_and_no_prices(self):
        text = access_pack.render(access_pack.portfolio_by_heading(self.db, 'Colombia'), None)
        self.assertIn('HS 0702 Tomatoes, fresh or chilled: 2 products', text)
        self.assertIn('coded to the heading only', text)
        self.assertIn('NO HS code yet', text)
        self.assertNotIn('price', text.lower())

    def test_the_market_opportunities_facts_are_counts_and_a_stale_warning(self):
        self.db.add_all([models.MarketOpportunityComparison(id=f'r{i}', product_name='Tomato', source_country='Colombia', target_country='Jamaica', hs_code='070200',
                                                            opportunity_rating='High', calculated_at='2026-10-03T10:00:00+00:00') for i in range(3)])
        self.db.commit()
        facts = access_pack.comparison_facts(self.db, 'Colombia', 'Jamaica')
        self.assertEqual((facts['matched'], facts['headings'], facts['stale']), (3, {'0702': {'High': 3}}, True))
        text = access_pack.render(access_pack.portfolio_by_heading(self.db, 'Colombia'), facts)
        self.assertIn('3 High', text)
        self.assertIn('may be out of date', text)
        self.assertIsNone(access_pack.comparison_facts(self.db, 'Colombia', 'Bahamas'))


class PromptTests(unittest.TestCase):
    def test_the_prompt_asks_for_access_not_price(self):
        prompt = claude_client._build_competitiveness_prompt('Colombia', '- HS 0702 Tomatoes: 2 products', 'Jamaica', 'PROFILE TEXT')
        self.assertIn('Market Access Brief', prompt)
        self.assertIn('Do NOT judge price competitiveness', prompt)
        self.assertIn('PROFILE TEXT', prompt)
        self.assertNotIn('avg price', prompt)

    def test_web_search_is_off_unless_asked_for(self):
        sent = []

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {'content': [{'type': 'text', 'text': '# Colombia → Jamaica — Market Access Brief\n\nBody'}], 'stop_reason': 'end_turn'}

        with mock.patch.object(claude_client.httpx, 'post', lambda url, json=None, **kw: sent.append(json) or Response()), mock.patch.object(claude_client, '_get_api_key', lambda: 'k'):
            claude_client.build_competitiveness_analysis('Colombia', 'pack', 'Jamaica', 'profile')
            claude_client.build_competitiveness_analysis('Colombia', 'pack', 'Jamaica', 'profile', web_search=True)
        self.assertNotIn('tools', sent[0])
        self.assertEqual(sent[1]['tools'][0]['name'], 'web_search')


class EndpointTests(AccessBriefTestCase):
    def setUp(self):
        super().setUp()
        self.db.add(models.CommercialCountry(id='jm1', company_id='co1', region_id='r1', name='Jamaica', country_code='JM'))
        self.db.commit()
        profiles = Path(self.tmp.name) / 'profiles'
        profiles.mkdir()
        (profiles / 'jm1.md').write_text('Jamaica profile', encoding='utf-8')
        self.captured = {}

        def fake_build(source, pack, target, profile, extra='', web_search=False):
            self.captured.update(source=source, pack=pack, target=target, profile=profile, web_search=web_search)
            return f'# {source} → {target} — Market Access Brief\n\nBody'

        for patch in (mock.patch.object(competitiveness, 'PROFILES_DIR', profiles), mock.patch.object(competitiveness, 'ANALYSES_DIR', Path(self.tmp.name) / 'analyses'), mock.patch.object(history_service, 'BACKEND', Path(self.tmp.name).resolve()),
                      mock.patch.object(competitiveness, 'build_competitiveness_analysis', fake_build),
                      mock.patch.object(competitiveness, 'business_context', lambda db, topic: ([], [])),
                      mock.patch.object(competitiveness, 'context_prompt_section', lambda context: '')):
            patch.start()
            self.addCleanup(patch.stop)
        app = FastAPI()
        app.include_router(competitiveness.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.url = '/companies/co1/commercial-countries/jm1/competitiveness'

    def test_the_build_needs_no_browser_summary_and_writes_the_brief(self):
        response = self.client.post(self.url, json={'source_country_name': 'Colombia'})
        self.assertEqual(response.json(), {'status': 'started'})
        self.assertEqual((self.captured['source'], self.captured['target'], self.captured['web_search']), ('Colombia', 'Jamaica', False))
        self.assertIn('HS 0702', self.captured['pack'])
        written = (Path(self.tmp.name) / 'analyses').glob('*.md')
        self.assertIn('Market Access Brief', next(written).read_text(encoding='utf-8'))
        self.assertEqual(history_store.latest('file:analyses/jm1__colombia.md')['reason'], 'market access brief built')

    def test_an_old_caller_that_still_sends_a_summary_works_and_web_search_can_be_requested(self):
        self.client.post(self.url, json={'source_country_name': 'Colombia', 'category_summary': [{'category': 'x'}], 'web_search': True})
        self.assertTrue(self.captured['web_search'])

    def test_a_source_with_no_stored_products_is_refused_with_a_reason(self):
        response = self.client.post(self.url, json={'source_country_name': 'Bahamas'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('No product data is stored for Bahamas', response.json()['detail'])


if __name__ == '__main__':
    unittest.main()
