"""The Tax Calculator saves its per-kg result as the import-tax multiplier of origin -> destination (the value Market Opportunities reads)."""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, tax_calc
from backend.database import Base, get_db
from backend.routers import tax_calculator


def make_client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[models.ProductTaxMultiplier.__table__])
    factory = sessionmaker(bind=engine)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(tax_calculator.router)
    app.dependency_overrides[get_db] = override
    return TestClient(app)


COLOMBIA_PAYLOAD = {
    'destination': 'Colombia',
    'origin': 'United States',
    'product_name': '  Hass Avocado ',
    'category': 'frutas',
    'hs_code': '080440',
    'price_usd_kg': 2.5,
    'tax_multiplier': 0.15,
    'tariff_code': '0804400000',
    'tariff_path': 'Frutas - Aguacates (paltas)',
    'status': 'ok',
    'note': 'From the Tax Calculator (DIAN).',
    'detail': [{'name': 'Gravamen arancelario', 'rate': '15%', 'per_usd': 0.15}, {'name': 'IVA', 'rate': '0% (EXCLUIDO)', 'per_usd': 0.0}],
}


class SaveMultiplierTests(unittest.TestCase):
    def test_saved_value_is_listed_for_the_pair_even_without_a_calculator(self):
        client = make_client()
        saved = client.post('/tax-calc/multipliers/save', json=COLOMBIA_PAYLOAD).json()
        self.assertEqual((saved['product_key'], saved['tax_multiplier'], saved['landed_multiplier'], saved['method']), ('hass avocado', 0.15, 1.15, 'tax_calculator'))
        listing = client.get('/tax-calc/multipliers', params={'destination': 'Colombia', 'origin': 'United States'}).json()
        self.assertFalse(listing['available'])  # no automatic calculator for Colombia: the saved rows are all there is
        self.assertEqual([row['product_key'] for row in listing['multipliers']], ['hass avocado'])
        self.assertEqual(listing['multipliers'][0]['detail'][0]['name'], 'Gravamen arancelario')

    def test_saving_again_replaces_the_value(self):
        client = make_client()
        client.post('/tax-calc/multipliers/save', json=COLOMBIA_PAYLOAD)
        client.post('/tax-calc/multipliers/save', json={**COLOMBIA_PAYLOAD, 'tax_multiplier': 0.4, 'status': 'review'})
        rows = client.get('/tax-calc/multipliers', params={'destination': 'Colombia', 'origin': 'United States'}).json()['multipliers']
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['tax_multiplier'], rows[0]['status']), (0.4, 'review'))

    def test_bad_input_is_rejected(self):
        client = make_client()
        self.assertEqual(client.post('/tax-calc/multipliers/save', json={**COLOMBIA_PAYLOAD, 'tax_multiplier': -1}).status_code, 422)
        self.assertEqual(client.post('/tax-calc/multipliers/save', json={**COLOMBIA_PAYLOAD, 'status': 'weird'}).status_code, 400)
        self.assertEqual(client.post('/tax-calc/multipliers/save', json={**COLOMBIA_PAYLOAD, 'product_name': '  '}).status_code, 400)

    def test_delete(self):
        client = make_client()
        client.post('/tax-calc/multipliers/save', json=COLOMBIA_PAYLOAD)
        params = {'destination': 'Colombia', 'origin': 'United States', 'product_key': 'Hass Avocado'}
        self.assertEqual(client.delete('/tax-calc/multipliers', params=params).status_code, 200)
        self.assertEqual(client.delete('/tax-calc/multipliers', params=params).status_code, 404)

    def test_automatic_computation_does_not_overwrite_a_saved_value(self):
        calculator = tax_calc.get('Jamaica')
        if not calculator.info()['ready']:
            self.skipTest('Jamaica tariff data not present')
        client = make_client()
        saved = {**COLOMBIA_PAYLOAD, 'destination': 'Jamaica', 'origin': 'Colombia', 'product_name': 'Tomato', 'tax_multiplier': 9.99, 'hs_code': '070200'}
        client.post('/tax-calc/multipliers/save', json=saved)
        compute = client.post(
            '/tax-calc/multipliers/compute',
            json={'destination': 'Jamaica', 'origin': 'Colombia', 'products': [{'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 1.5}, {'name': 'Other tomato', 'hs_code': '070200', 'price_usd_kg': 1.5}]},
        ).json()
        self.assertEqual(compute['by_status'].get('saved'), 1)
        rows = {row['product_key']: row for row in client.get('/tax-calc/multipliers', params={'destination': 'Jamaica', 'origin': 'Colombia'}).json()['multipliers']}
        self.assertEqual(rows['tomato']['tax_multiplier'], 9.99)  # kept
        self.assertNotEqual(rows['other tomato']['tax_multiplier'], 9.99)  # computed automatically
        self.assertEqual(rows['other tomato']['method'] != 'tax_calculator', True)


if __name__ == '__main__':
    unittest.main()
