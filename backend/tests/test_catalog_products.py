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

from backend import models, modification_reports
from backend.database import Base, get_db
from backend.routers import catalog_products, knowledge_base


class DeleteCatalogProductsTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        reports = Path(self.tmp.name) / 'reports'
        patches = [
            mock.patch.object(modification_reports, 'REPORTS_DIR', reports),
            mock.patch.object(knowledge_base, 'MODIFICATION_REPORTS_DIR', reports),
            mock.patch.object(knowledge_base.rag, 'KNOWLEDGE_BASE_DIR', Path(self.tmp.name) / 'kb'),
            mock.patch.object(knowledge_base.rag, 'rag_path', lambda doc_id: Path(self.tmp.name) / 'kb' / f'{doc_id}.rag.json'),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.reports = reports
        custom = [
            {'id': 'a1', 'category': 'Fruit', 'name': 'Mango', 'unit': 'kg', 'price': 3.0, 'currency': 'JMD', 'norm': {'price_per_kg': 3.0}},
            {'id': 'a2', 'category': 'Fruit', 'name': 'Papaya', 'unit': 'each', 'price': 5.0, 'currency': 'JMD'},
            {'id': 'a3', 'category': 'Veg', 'name': 'Okra', 'unit': 'kg', 'price': 2.0, 'currency': 'JMD'},
        ]
        retail = [
            {'category': 'Retail Produce', 'product_en': 'Limes', 'unit': 'USD/each', 'price': 0.5, 'detail': True},
            {'category': 'Retail Produce', 'product_en': 'Limes', 'unit': 'USD/each', 'price': 0.6, 'detail': False},
        ]
        with self.Session() as db:
            db.add(models.ProductSource(id='s1', country_name='Jamaica', name='Shop', product_count=3, analysis_type='retail', created_at='2026-11-01'))
            db.add(models.PriceComparisonSnapshot(source='custom_s1', data_json=json.dumps(custom), fetched_at='2026-11-01'))
            db.add(models.PriceComparisonSnapshot(source='usa_retail_produce', data_json=json.dumps(retail), fetched_at='2026-11-01'))
            db.commit()
        app = FastAPI()
        app.include_router(catalog_products.router)

        def override():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def products(self, key):
        with self.Session() as db:
            return json.loads(db.query(models.PriceComparisonSnapshot).filter_by(source=key).one().data_json)

    def test_deletes_only_the_selected_products_and_writes_a_report(self):
        body = {
            'items': [{'source': 'custom_s1', 'id': 'a1', 'category': 'Fruit', 'name': 'Mango', 'unit': 'kg'}, {'source': 'custom_s1', 'id': 'a3', 'category': 'Veg', 'name': 'Okra', 'unit': 'kg'}],
            'deleted_by': 'Ana',
        }
        result = self.client.post('/catalog-products/delete', json=body).json()
        self.assertEqual((result['removed'], result['requested']), (2, 2))
        self.assertEqual([p['name'] for p in self.products('custom_s1')], ['Papaya'])
        with self.Session() as db:
            source = db.get(models.ProductSource, 's1')
            self.assertEqual(source.product_count, 1)
            snapshot = db.query(models.PriceComparisonSnapshot).filter_by(source='custom_s1').one()
            self.assertEqual(snapshot.fetched_at, '2026-11-01')  # the sync time is not touched
            documents = db.query(models.KnowledgeDocument).all()
        report = (self.reports / result['report']).read_text(encoding='utf-8')
        self.assertIn('Done by:** Ana', report)
        self.assertIn('| 1 | Jamaica | Shop | Fruit | Mango |', report)
        self.assertIn('Okra', report)
        self.assertNotIn('Papaya', report)
        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].report_key.startswith('modification_report:'))
        self.assertIn('2 products deleted', documents[0].name)

    def test_an_explicit_null_field_tells_apart_two_rows_of_the_same_product(self):
        item = {'source': 'usa_retail_produce', 'category': 'Retail Produce', 'name': 'Limes', 'unit': 'USD/each', 'detail': False}
        self.assertEqual(self.client.post('/catalog-products/delete', json={'items': [item]}).json()['removed'], 1)
        self.assertEqual([p['detail'] for p in self.products('usa_retail_produce')], [True])

    def test_a_product_that_is_gone_is_a_404_and_nothing_changes(self):
        body = {'items': [{'source': 'custom_s1', 'id': 'zzz', 'name': 'Nothing'}]}
        self.assertEqual(self.client.post('/catalog-products/delete', json=body).status_code, 404)
        self.assertEqual(len(self.products('custom_s1')), 3)
        self.assertEqual(self.client.post('/catalog-products/delete', json={'items': []}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
