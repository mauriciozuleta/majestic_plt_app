"""The catalog scope: which downloaded products are in the main catalog and which go to the secondary (discarded) list. The classifier is checked on real product names from the
supermarket catalogs (a produce category that holds seasoning, a canned ham, a cheese brand called "Cracker Barrel" ...), then the whole flow on an in-memory database: the verdict is
stored with each product, discarded rows get no weight lookup, the consumers (portfolio, Market Opportunities, HS queue) see only the main catalog, and a person's move survives a
new download."""

import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.catalog_normalization import hs_store, scope, scope_store
from backend.database import Base, get_db
from backend.market_opportunities import collect
from backend.portfolio import service as portfolio_service
from backend.routers import catalog_scope
from backend.snapshot_store import list_snapshots, save_snapshot

# (name, store category, HS6 or '', expected status)
CASES = [
    # in: fresh produce, meat and fish, processed meat that needs the cold chain, cheese, eggs
    ('Apples Granny Smith', 'Fresh Produce > Apple', '080810', 'main'),
    ('Rtc Chicken Mixed Parts Perlb', 'MEAT SEAFOOD', '020713', 'main'),
    ('Early Dawn Shrimp 21/25CTP&D Tail On', 'MEAT SEAFOOD', '030617', 'main'),
    ('Boneless Salt Beef', 'Frozen Meat & Seafood', '021020', 'main'),
    ('Fiedlers Black Forest Ham Deli 10kg', 'MEAT SEAFOOD', '160241', 'main'),
    ('Johnsonville Sausage Sweet 19Oz', 'Groceries ; Butchery', '160100', 'main'),
    ('EVE Picnic Ham Brown Sugar Flavour', 'Frozen Meat & Seafood', '021011', 'main'),
    ('Kraft Cheese 8oz Colby', 'DAIRY & EGGS', '040690', 'main'),
    ('Cracker Barrel Baby Swiss 8Oz', 'Groceries ; Dairy & Eggs ; Butter & Eggs', '040690', 'main'),  # the brand holds the word "cracker"
    ('Crystal Farms Cream Chesse 8oz Original', 'DAIRY & EGGS', '040610', 'main'),  # a typo in the name: the HS code says cheese
    ('Large Eggs 12 Count', 'DAIRY & EGGS', '040721', 'main'),
    ('Honey Gold Potatoes One Bite 24oz', 'Produce ; Ground Provisions', '070190', 'main'),  # "honey" in a potato
    ('Honey Dew Melon Per Lb Local', 'PRODUCE', '080719', 'main'),
    ('Squash Spaghetti', 'Produce ; Produce Misc', '070993', 'main'),  # "spaghetti" in a squash
    ('Red Seedless Grape 2 Lbs', 'Groceries ; Produce ; Fresh Fruit', '080610', 'main'),  # fresh grapes (080620 is raisins)
    ('Thyme (Local)', 'Retail Produce', '091040', 'main'),  # a fresh herb
    ('Ginger (Imported)', 'Urban Municipal Produce', '091011', 'main'),
    ('Pimento (M)(20lb)', 'Condiments And Spices', '070960', 'main'),  # fresh peppers filed under spices
    ('Mushrooms Organic', 'Produce ; Vegetables', '', 'main'),  # no HS code: the category says produce
    ('BACHIN', 'Uncategorized', '', 'main'),  # nothing says it is out: never dropped for lacking a code (flagged to check)
    # out: other dairy, canned or shelf-stable meat, frozen / canned / dried produce, nuts, grains, bakery, sweets, drinks, sauces, spices, non-food
    ('Anchor Full Cream Milk 300g Sachet', 'DAIRY & EGGS', '040221', 'secondary'),
    ('Taster H/M Yogurt 8oz Cherry', 'DAIRY & EGGS', '040310', 'secondary'),
    ('Imperial Margarine 227G', 'DAIRY & EGGS ; DAIRY & EGGS > Butter', '151790', 'secondary'),
    ('Fam Choice Ham Chopped 300 gr', 'Canned Products', '160241', 'secondary'),  # canned ham: sea freight
    ('Corned Beef 340g', 'Grocery', '160250', 'secondary'),
    ('Pink Salmon Wild', 'Grocery', '160411', 'secondary'),  # preserved fish filed as grocery
    ('Atlantic Pearl B/Less Salted Fish 1LB', 'MEAT SEAFOOD', '030539', 'secondary'),  # dried / salted fish keeps without a cold chain
    ('Silk 946ML/32OZ Almond Unsweetned', 'DAIRY & EGGS ; DAIRY & EGGS > Milk', '220299', 'secondary'),
    ('Roma Pasta Spaghetti 500g', 'Pasta', '190219', 'secondary'),
    ('Waitrose Rice Basmati Brown 250g', 'Pasta', '100620', 'secondary'),
    ('Toaster Strudel Cherry', 'Groceries ; Frozen Items ; Frozen Pastries', '190590', 'secondary'),
    ('Chief Creole Seasoning 300ml', 'PRODUCE', '210390', 'secondary'),  # misplaced in the produce category
    ('Frozen Corn Ribs', 'Frozen Food ; Frozen Veg/Fruit', '071040', 'secondary'),
    ('Chiquita Blueberries Whole 12 oz', 'Frozen Fruits & Vegetables', '081190', 'secondary'),
    ('Semaj Dried Jamaican Sorrel 2oz', 'Produce ; Dried Fruits', '081340', 'secondary'),
    ('Green Lentils', 'Grocery', '071340', 'secondary'),  # dried legumes sit in the vegetable chapter
    ('Sultana Raisins', 'Produce ; Dried Fruits', '080620', 'secondary'),
    ('Imported Peanut Roasted 284G', 'Grocery', '200811', 'secondary'),
    ('Loma Linda Big Franks Meatless Vegan', 'Grocery', '210610', 'secondary'),
    ('Idahoan Mashed Potatoes Four Cheese 4oz', 'Grocery', '110520', 'secondary'),  # not a cheese
    ('Hot Pocket Ham & Cheese 255G', 'Frozen Meals', '190590', 'secondary'),
    ('Drink Sparkling Raspberry Peach', 'Grocery', '220210', 'secondary'),
    ('Pascual Yogurt 125g x 4 Lemon', 'DAIRY & EGGS', '040310', 'secondary'),
    ('Charmin Ultra Soft 6’s', 'Grocery', '', 'secondary'),  # no code, a store category outside the scope
]


class ClassifierTests(unittest.TestCase):
    def test_the_rules_on_real_names(self):
        wrong = []
        for name, category, hs6, expected in CASES:
            verdict = scope.classify({'name': name, 'category': category, 'hs': {'hs6': hs6} if hs6 else None})
            if verdict['status'] != expected:
                wrong.append((name, expected, verdict))
        self.assertEqual(wrong, [])

    def test_a_verdict_says_why_and_how_sure(self):
        verdict = scope.classify({'name': 'Chief Creole Seasoning 300ml', 'category': 'PRODUCE', 'hs': {'hs6': '210390'}})
        self.assertEqual((verdict['status'], verdict['rule'], verdict['confidence']), ('secondary', 'sauces_condiments', 'high'))
        unsure = scope.classify({'name': 'BACHIN', 'category': 'Uncategorized', 'hs': None})
        self.assertEqual(unsure['confidence'], 'low')

    def test_a_person_wins_over_the_rules(self):
        verdict = scope.classify({'name': 'Roma Pasta Spaghetti 500g', 'category': 'Pasta', 'hs': {'hs6': '190219'}})
        moved = scope.with_override(verdict, 'main')
        self.assertEqual((moved['status'], moved['rule'], moved['confidence'], moved['rules_said']), ('main', 'override', 'user', 'secondary'))
        self.assertIs(scope.with_override(verdict, None), verdict)

    def test_the_rule_patterns_are_clean_regular_expressions(self):
        # a pattern written with a lone backslash turns "\b" into a backspace character: it compiles but never matches, so check for control characters too
        def strings(value):
            if isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, str):
                yield value

        for text in strings(scope.load_rules()):
            self.assertFalse(any(ord(ch) < 32 for ch in text), repr(text[:60]))

    def test_what_a_main_product_still_needs(self):
        ready = {'scope': {'status': 'main', 'confidence': 'high'}, 'hs': {'hs6': '070200', 'obsolete': False}, 'norm': {'method': 'stated_weight'}}
        self.assertEqual(scope.review_issues(ready), [])
        self.assertEqual(scope.review_issues({**ready, 'hs': {'hs6': None}}), ['no_hs'])
        self.assertEqual(scope.review_issues({**ready, 'hs': {'hs6': '020710', 'obsolete': True}}), ['old_hs'])
        self.assertEqual(scope.review_issues({**ready, 'norm': {'method': 'needs_research'}}), ['no_price_per_kg'])
        self.assertEqual(scope.review_issues({**ready, 'norm': {'method': 'unconvertible'}}), ['no_price_per_kg'])
        self.assertEqual(scope.review_issues({**ready, 'scope': {'status': 'main', 'confidence': 'low'}}), ['unsure_scope'])
        everything = {'scope': {'status': 'main', 'confidence': 'low'}, 'hs': None, 'norm': {'method': 'needs_research'}}
        self.assertEqual(scope.review_issues(everything), ['no_hs', 'no_price_per_kg', 'unsure_scope'])
        self.assertEqual(scope.review_issues({**everything, 'scope': {'status': 'secondary', 'confidence': 'high'}}), [])  # a discarded product has nothing to fix

    def test_only_the_supermarket_catalogs_are_classified(self):
        self.assertTrue(scope.applies_to('custom_abc'))
        for source in ('la_mayorista', 'corabastos', 'usa_beef', 'usa_retail_produce'):
            self.assertFalse(scope.applies_to(source))
        self.assertTrue(scope.is_main({'name': 'x'}))  # no scope block: main


JAMAICA = [
    # name, category, unit, price, HS6
    ('Lulo', 'PRODUCE', 'unit', 11.95, '081090'),  # fresh, a count unit that no table knows: waits for research
    ('Fiedlers Black Forest Ham Deli 10kg', 'MEAT SEAFOOD', 'kg', 900.0, '160241'),
    ('Kraft Cheese 8oz Colby', 'DAIRY & EGGS', 'oz', 8.5, '040690'),
    ('Pascual Yogurt 125g x 4 Lemon', 'DAIRY & EGGS', 'unit', 29.0, '040310'),  # discarded: no weight is looked up
    ('Toaster Strudel Cherry', 'Frozen Pastries', 'unit', 11.0, '190590'),
    ('Chief Creole Seasoning 300ml', 'PRODUCE', 'ml', 7.5, '210390'),
    ('Tomato (Local)', 'Rural Municipal Produce', 'kg', 3.0, '070200'),
]


class ScopeFlowTests(unittest.TestCase):
    def setUp(self):
        database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(database)
        self.db = sessionmaker(bind=database)()
        self.addCleanup(self.db.close)
        self.db.add(models.ProductSource(id='s1', country_name='Jamaica', name='Store One', status='ok', product_count=len(JAMAICA), created_at='2026-01-01', currency='JMD'))
        for name, _category, _unit, _price, hs6 in JAMAICA:
            self.db.add(models.ProductHsAssignment(country='Jamaica', product_key=name.lower(), hs_code=hs6, hs_level=6, status='confirmed'))
        self.db.commit()
        self.download()
        app = FastAPI()
        app.include_router(catalog_scope.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def download(self):
        products = [{'id': str(i), 'name': name, 'category': category, 'unit': unit, 'price': price, 'currency': 'JMD'} for i, (name, category, unit, price, _hs) in enumerate(JAMAICA)]
        save_snapshot(self.db, 'custom_s1', products)

    def stored(self) -> dict:
        return {p['name']: p for p in list_snapshots(self.db, ['custom_s1'])[0]['products']}

    def test_every_product_gets_a_scope_and_the_discarded_ones_get_no_weight_lookup(self):
        stored = self.stored()
        self.assertEqual({name: product['scope']['status'] for name, product in stored.items()},
                         {'Lulo': 'main', 'Fiedlers Black Forest Ham Deli 10kg': 'main', 'Kraft Cheese 8oz Colby': 'main', 'Pascual Yogurt 125g x 4 Lemon': 'secondary',
                          'Toaster Strudel Cherry': 'secondary', 'Chief Creole Seasoning 300ml': 'secondary', 'Tomato (Local)': 'main'})
        self.assertEqual(stored['Lulo']['norm']['method'], 'needs_research')  # a main product waits for its weight
        self.assertEqual(stored['Toaster Strudel Cherry']['norm']['method'], 'unconvertible')  # a discarded one never does
        self.assertIn('Not in the catalog scope', stored['Toaster Strudel Cherry']['norm']['note'])
        self.assertEqual(stored['Tomato (Local)']['norm']['price_per_kg'], 3.0)  # what a row states is still converted

    def test_the_summary_and_the_discarded_list(self):
        summary = self.client.get('/api/catalog-scope/summary').json()
        self.assertEqual((summary['total']['main'], summary['total']['secondary']), (4, 3))
        self.assertEqual(summary['sources'][0]['name'], 'Store One')
        self.assertIn('Dairy other than cheese and eggs: not in the catalog', summary['reasons'])
        items = self.client.get('/api/catalog-scope/items').json()
        self.assertEqual(items['total'], 3)
        self.assertEqual({item['name'] for item in items['items']}, {'Pascual Yogurt 125g x 4 Lemon', 'Toaster Strudel Cherry', 'Chief Creole Seasoning 300ml'})
        first = next(item for item in items['items'] if item['name'].startswith('Chief'))
        self.assertEqual((first['country'], first['source_name'], first['hs6'], first['status']), ('Jamaica', 'Store One', '210390', 'secondary'))
        self.assertEqual(self.client.get('/api/catalog-scope/items', params={'q': 'yogurt'}).json()['total'], 1)
        self.assertEqual(self.client.get('/api/catalog-scope/items', params={'country': 'Bahamas'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/catalog-scope/items', params={'status': 'main'}).json()['total'], 4)

    def test_the_three_portfolios_of_a_country(self):
        summary = self.client.get('/api/catalog-scope/summary').json()['total']
        self.assertEqual((summary['main'], summary['ready'], summary['check'], summary['secondary']), (4, 3, 1, 3))  # main = ready + check
        check = self.client.get('/api/catalog-scope/items', params={'status': 'check'}).json()
        self.assertEqual([item['name'] for item in check['items']], ['Lulo'])  # a count-priced fruit with no weight yet
        self.assertEqual(check['items'][0]['issues'], [{'code': 'no_price_per_kg', 'label': 'No price per kg yet'}])
        ready = self.client.get('/api/catalog-scope/items', params={'status': 'ready'}).json()
        self.assertEqual(sorted(item['name'] for item in ready['items']), ['Fiedlers Black Forest Ham Deli 10kg', 'Kraft Cheese 8oz Colby', 'Tomato (Local)'])
        self.assertEqual(self.client.get('/api/catalog-scope/items', params={'status': 'main'}).json()['total'], 4)
        self.assertEqual(self.client.get('/api/catalog-scope/items', params={'status': 'secondary'}).json()['total'], 3)
        self.assertEqual(self.stored()['Lulo']['review'], {'issues': ['no_price_per_kg']})  # decided at save time, on the server
        self.assertEqual(self.stored()['Tomato (Local)']['review'], {'issues': []})
        self.assertEqual(self.stored()['Toaster Strudel Cherry']['review'], {'issues': []})  # a discarded product has nothing to fix
        # fixing the open issue moves the product from "to check" to "catalog": a weight a person typed
        from backend.catalog_normalization.store import DbStore, ItemWeight

        DbStore(self.db).put(ItemWeight('Lulo', 'each', 0.09, confidence='user', note='typed'))
        scope_store.reclassify(self.db)
        summary = self.client.get('/api/catalog-scope/summary').json()['total']
        self.assertEqual((summary['ready'], summary['check']), (4, 0))

    def test_the_consumers_see_only_the_main_catalog(self):
        names = [product['name'] for group in portfolio_service.country_products(self.db) if group['country'] == 'Jamaica' for product in group['products']]
        self.assertEqual(sorted(names), ['Fiedlers Black Forest Ham Deli 10kg', 'Kraft Cheese 8oz Colby', 'Lulo', 'Tomato (Local)'])
        self.assertEqual(sorted(p['displayName'] for p in collect.custom_products(self.db, 'Jamaica')), sorted(names))
        queued = {item['name'] for item in hs_store.queue(self.db, 'Jamaica', 100, include_confirmed=True)['items']}
        self.assertNotIn('Toaster Strudel Cherry', queued)

    def test_moving_a_product_back_survives_a_new_download(self):
        moved = self.client.post('/api/catalog-scope/move', json={'items': [{'source': 'custom_s1', 'name': 'Pascual Yogurt 125g x 4 Lemon'}], 'to': 'main'}).json()
        self.assertEqual((moved['moved'], moved['to']), (1, 'main'))
        yogurt = self.stored()['Pascual Yogurt 125g x 4 Lemon']
        self.assertEqual((yogurt['scope']['status'], yogurt['scope']['rule'], yogurt['scope']['confidence']), ('main', 'override', 'user'))
        self.assertEqual(self.client.get('/api/catalog-scope/summary').json()['total']['moved_by_you'], 1)
        self.assertEqual(self.client.get('/api/catalog-scope/items').json()['total'], 2)
        self.download()  # the next scrape delivers it again: the choice is kept
        self.assertEqual(self.stored()['Pascual Yogurt 125g x 4 Lemon']['scope']['status'], 'main')
        # and a main product can be set aside
        self.client.post('/api/catalog-scope/move', json={'items': [{'source': 'custom_s1', 'name': 'tomato (local)'}], 'to': 'secondary'})
        self.assertEqual(self.stored()['Tomato (Local)']['scope']['status'], 'secondary')
        self.assertEqual(self.client.get('/api/catalog-scope/items').json()['total'], 3)

    def test_a_move_is_recorded_in_the_data_history(self):
        from backend import data_history

        before = len(data_history.store.versions('snapshot:custom_s1'))
        self.client.post('/api/catalog-scope/move', json={'items': [{'source': 'custom_s1', 'name': 'Toaster Strudel Cherry'}], 'to': 'main'})
        versions = data_history.store.versions('snapshot:custom_s1')
        self.assertEqual(len(versions), before + 1)
        self.assertIn('Returned to the main catalog', versions[0]['reason'])

    def test_bad_requests(self):
        self.assertEqual(self.client.post('/api/catalog-scope/move', json={'items': [], 'to': 'main'}).status_code, 400)
        self.assertEqual(self.client.post('/api/catalog-scope/move', json={'items': [{'source': 'custom_s1', 'name': 'x'}], 'to': 'nowhere'}).status_code, 400)
        self.assertEqual(self.client.post('/api/catalog-scope/move', json={'items': [{'source': 'la_mayorista', 'name': 'Acelga'}], 'to': 'secondary'}).json()['moved'], 0)

    def test_the_rules_can_be_applied_again_and_old_catalogs_get_the_block_at_start_up(self):
        for row in self.db.query(models.PriceComparisonSnapshot).all():  # a catalog stored before this module existed
            products = json.loads(row.data_json)
            for product in products:
                product.pop('scope', None)
            row.data_json = json.dumps(products)
        self.db.commit()
        self.assertGreater(scope_store.ensure_scoped(self.db), 0)
        self.assertTrue(all('scope' in product for product in self.stored().values()))
        self.assertEqual(scope_store.ensure_scoped(self.db), 0)  # once
        self.assertEqual(self.client.post('/api/catalog-scope/reclassify').json()['sources'], 1)


if __name__ == '__main__':
    unittest.main()
