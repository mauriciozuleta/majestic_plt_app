"""The Python portfolio must reproduce what the JavaScript produced on the frozen inputs (backend/tests/js_parity/capture.py saved both). If a difference is intended, it is
a separate, named change: re-capture or edit the expectation in the same commit and say why."""

import json
import math
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, portfolio
from backend.database import Base, get_db
from backend.routers import comtrade, portfolio as portfolio_router
from backend.tests.js_parity import inputs as parity

# the fields the Python rows have ON TOP of what the JavaScript merge produced (the English name travels with the row now)
ADDED_FIELDS = ('name_en', 'translated', 'translation_tier')
EXPECTED = json.loads((parity.FIXTURES / 'outputs.json').read_text(encoding='utf-8'))


def same(actual, expected, path='') -> list[str]:
    """Differences between a Python value and the JSON the JavaScript produced. A key the JavaScript omitted (undefined) equals None in Python; floats compare closely."""
    problems = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f'{path}: expected an object, got {type(actual).__name__}']
        for key in expected:
            if key not in actual:
                problems.append(f'{path}.{key}: missing')
            else:
                problems += same(actual[key], expected[key], f'{path}.{key}')
        for key in set(actual) - set(expected):
            if actual[key] is not None:
                problems.append(f'{path}.{key}: extra value {actual[key]!r}')
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f'{path}: list length {len(actual) if isinstance(actual, list) else actual!r} != {len(expected)}']
        for index, (a, e) in enumerate(zip(actual, expected)):
            problems += same(a, e, f'{path}[{index}]')
    elif isinstance(expected, float) or isinstance(actual, float):
        if actual is None or expected is None or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
            problems.append(f'{path}: {actual!r} != {expected!r}')
    elif actual != expected:
        problems.append(f'{path}: {actual!r} != {expected!r}')
    return problems


class PortfolioParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        cls.Session = sessionmaker(bind=engine)
        with cls.Session() as session:
            parity.load_inputs(session, parity.read_inputs())

    def setUp(self):
        self.db = self.Session()
        self.addCleanup(self.db.close)

    def test_the_colombia_merge_and_translations_equal_the_javascript(self):
        rows = portfolio.colombia_merged(self.db)
        expected = EXPECTED['colombia_merged']
        self.assertEqual(len(rows), len(expected))
        problems = []
        for row, js in zip(rows, expected):
            translation = js.pop('_translation')
            problems += same({k: v for k, v in row.items() if k not in ADDED_FIELDS}, js, f"[{js['id']}]")
            if (row['name_en'], row['translated']) != (translation['text'], translation['isTranslated']):
                problems.append(f"[{js['id']}] translation {(row['name_en'], row['translated'])} != {(translation['text'], translation['isTranslated'])}")
        self.assertEqual(problems[:10], [])

    def test_the_directory_equals_the_javascript_portfolio(self):
        rows = portfolio.directory(self.db)
        expected = EXPECTED['portfolio']
        self.assertEqual(len(rows), len(expected))
        by_key = {(row['country'], row['name'].lower()): row for row in rows}
        self.assertEqual(len(by_key), len(rows))
        problems = []
        for js in expected:
            row = by_key.get((js['country'], js['name'].lower()))
            if row is None:
                problems.append(f"missing {js['country']} / {js['name']}")
                continue
            problems += same(row, js, f"[{js['country']}|{js['name']}]")
        self.assertEqual(problems[:10], [])
        # a stable order a person can rely on: by name (case-insensitive), then country
        self.assertEqual([(r['name'].casefold(), r['country'].casefold()) for r in rows], sorted((r['name'].casefold(), r['country'].casefold()) for r in rows))

    def test_the_category_coverage_equals_the_javascript(self):
        self.assertEqual(same(portfolio.category_coverage(self.db), EXPECTED['coverage'])[:10], [])
        self.assertEqual(list(portfolio.category_coverage(self.db)), sorted(EXPECTED['coverage']))

    def test_sam_and_tam_cover_every_chapter_of_the_coverage(self):
        self.assertEqual(portfolio.qualifying_chapters(self.db), sorted(EXPECTED['coverage']))


class PortfolioApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        cls.Session = sessionmaker(bind=engine)
        with cls.Session() as session:
            parity.load_inputs(session, parity.read_inputs())
        app = FastAPI()
        app.include_router(portfolio_router.router)
        cls.db = cls.Session()
        app.dependency_overrides[get_db] = lambda: cls.db
        cls.client = TestClient(app)

    def test_endpoints(self):
        directory = self.client.get('/api/portfolio/directory').json()['rows']
        self.assertEqual(len(directory), len(EXPECTED['portfolio']))
        self.assertTrue(all(row['country'] == 'Jamaica' for row in self.client.get('/api/portfolio/directory', params={'country': 'jamaica'}).json()['rows']))
        self.assertEqual(list(self.client.get('/api/portfolio/category-coverage').json()), sorted(EXPECTED['coverage']))
        self.assertEqual(self.client.get('/api/portfolio/qualifying-chapters').json()['chapters'], sorted(EXPECTED['coverage']))
        self.assertEqual(len(self.client.get('/api/portfolio/colombia').json()['rows']), len(EXPECTED['colombia_merged']))
        products = self.client.get('/api/portfolio/products', params={'country': 'Colombia'}).json()
        self.assertEqual(products['country'], 'Colombia')
        self.assertIn('hs', products['products'][0])
        self.assertEqual(self.client.get('/api/portfolio/products', params={'country': 'Atlantis'}).status_code, 404)


class SamScopeTests(unittest.TestCase):
    """SAM and TAM take their chapters from the server's coverage when none is stored or given (they used to need the browser to ask for them first)."""

    def setUp(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        with sessionmaker(bind=engine)() as session:
            parity.load_inputs(session, parity.read_inputs())

    def test_a_first_refresh_uses_the_coverage_chapters(self):
        captured = {}

        def fake_compute(db, chapter_list, flow):
            captured['chapters'] = chapter_list
            return {'flow': flow, 'default_year': 2025, 'categories': [], 'regions': []}

        from unittest import mock

        with mock.patch.object(comtrade, '_compute_sam_overview_data', fake_compute):
            comtrade.refresh_sam_overview(self.db, None, 'M')
        self.assertEqual(captured['chapters'], sorted(EXPECTED['coverage']))


if __name__ == '__main__':
    unittest.main()
