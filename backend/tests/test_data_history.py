import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import market_size_store, models, snapshot_store
from backend.data_history import HeldForApproval, guard, service, store
from backend.database import Base, get_db
from backend.routers import data_history as history_router
from backend.routers import product_sources, usa_sourcing


def products(count, price=1.0):
    return [{'id': f'p{i}', 'category': 'Beef', 'name': f'Item {i}', 'unit': 'lb', 'price': price + i, 'currency': 'USD'} for i in range(count)]


class HistoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(store.use_database, store.database_path())
        store.use_database(Path(self.tmp.name) / 'history.db')
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.addCleanup(self.db.close)

    def live(self, source):
        return snapshot_store.list_snapshots(self.db, [source])[0]['products']


class StoreTests(HistoryTestCase):
    def test_identical_content_adds_no_version_and_changes_add_one(self):
        first = store.record('snapshot:usa_beef', 'json', products(3), reason='t')
        self.assertEqual(first['version'], 1)
        self.assertIsNone(store.record('snapshot:usa_beef', 'json', products(3), reason='t'))
        self.assertEqual(store.record('snapshot:usa_beef', 'json', products(4), reason='t')['version'], 2)
        self.assertEqual([v['version'] for v in store.versions('snapshot:usa_beef')], [2, 1])

    def test_load_returns_the_exact_data_and_unknown_version_raises(self):
        store.record('snapshot:usa_beef', 'json', products(2), reason='t')
        self.assertEqual(store.load('snapshot:usa_beef', 1), ('json', products(2)))
        with self.assertRaises(KeyError):
            store.load('snapshot:usa_beef', 9)

    def test_actor_is_recorded(self):
        with store.acting_as('assistant'):
            store.record('snapshot:usa_beef', 'json', products(1), reason='t')
        self.assertEqual(store.latest('snapshot:usa_beef')['actor'], 'assistant')

    def test_prune_keeps_the_newest_pinned_and_the_latest(self):
        store.record('snapshot:usa_beef', 'json', products(1), reason='t')
        store.pin('snapshot:usa_beef', 1)
        for count in range(2, 41):
            store.record('snapshot:usa_beef', 'json', products(count), reason='t')
        store.record('snapshot:usa_beef', 'json', products(50), reason='t')
        kept = [v['version'] for v in store.versions('snapshot:usa_beef')]
        self.assertIn(1, kept)  # pinned
        self.assertEqual(kept[0], 41)  # the latest
        self.assertLessEqual(len(kept), 32)
        self.assertNotIn(2, kept)


class GuardTests(unittest.TestCase):
    def test_empty_and_big_drops_are_findings_small_ones_are_not(self):
        self.assertTrue(guard.check_products(products(20), []))
        self.assertTrue(guard.check_products(products(20), products(8)))
        self.assertEqual(guard.check_products(products(20), products(15)), [])
        self.assertEqual(guard.check_products(products(6), products(4)), [])  # too small a list to judge
        self.assertEqual(guard.check_products(None, []), [])  # nothing stored yet

    def test_market_size_total_drop(self):
        old = {'categories': [{'value': 100.0}] * 12}
        self.assertTrue(guard.check_market_size('tam', old, {'categories': [{'value': 100.0}] * 8}))
        self.assertEqual(guard.check_market_size('tam', old, {'categories': [{'value': 100.0}] * 12}), [])
        self.assertEqual(guard.check_market_size('tam', None, {'categories': []}), [])


class SnapshotTests(HistoryTestCase):
    def test_save_records_a_version_and_a_repeat_adds_none(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(12))
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(12))
        self.assertEqual(len(store.versions('snapshot:usa_beef')), 1)
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(13))
        self.assertEqual(len(store.versions('snapshot:usa_beef')), 2)

    def test_caches_are_not_versioned(self):
        snapshot_store.save_snapshot(self.db, 'comtrade_categories_M_170_2025', [{'x': 1}])
        self.assertEqual(store.scopes(), [])

    def test_suspicious_refresh_is_held_and_the_live_data_stays(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        with self.assertRaises(HeldForApproval) as caught:
            snapshot_store.save_snapshot(self.db, 'usa_beef', [], guard=True)
        self.assertEqual(len(self.live('usa_beef')), 20)
        self.assertEqual(len(store.versions('snapshot:usa_beef')), 1)
        pending = store.held_updates()
        self.assertEqual([h['id'] for h in pending], [caught.exception.held_id])
        self.assertIn('no products', pending[0]['findings'][0])

    def test_a_first_save_and_a_healthy_refresh_are_never_held(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(1), guard=True)
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(1) + products(5, 9), guard=True)
        self.assertEqual(store.held_updates(), [])

    def test_unguarded_save_and_force_skip_the_check(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        snapshot_store.save_snapshot(self.db, 'usa_beef', [], guard=False)  # a person's own file / deletion
        self.assertEqual(self.live('usa_beef'), [])

    def test_approve_applies_the_held_update(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        with self.assertRaises(HeldForApproval) as caught:
            snapshot_store.save_snapshot(self.db, 'usa_beef', products(5), guard=True)
        compare = service.compare_with_live(self.db, caught.exception.held_id)
        self.assertEqual((compare['old_count'], compare['new_count']), (20, 5))
        service.approve(self.db, caught.exception.held_id, 'tester')
        self.assertEqual(len(self.live('usa_beef')), 5)
        self.assertEqual(store.get_held(caught.exception.held_id)['status'], 'approved')
        self.assertEqual(len(store.versions('snapshot:usa_beef')), 2)
        with self.assertRaises(ValueError):
            service.approve(self.db, caught.exception.held_id)

    def test_reject_leaves_the_live_data(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        with self.assertRaises(HeldForApproval) as caught:
            snapshot_store.save_snapshot(self.db, 'usa_beef', [], guard=True)
        service.reject(caught.exception.held_id)
        self.assertEqual(len(self.live('usa_beef')), 20)
        self.assertEqual(store.held_updates(), [])
        self.assertEqual(store.get_held(caught.exception.held_id)['status'], 'rejected')

    def test_a_later_good_refresh_supersedes_the_hold(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        with self.assertRaises(HeldForApproval):
            snapshot_store.save_snapshot(self.db, 'usa_beef', [], guard=True)
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(21), guard=True)
        self.assertEqual(store.held_updates(), [])

    def test_restore_puts_an_old_version_back_as_a_new_version(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(12))
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(30))
        result = service.restore(self.db, 'snapshot:usa_beef', 1)
        self.assertEqual(result['products'], 12)
        self.assertEqual(len(self.live('usa_beef')), 12)
        versions = store.versions('snapshot:usa_beef')
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0]['reason'], 'restored version 1')

    def test_delete_marker_cannot_be_restored(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(3))
        store.record_deleted('snapshot:usa_beef', reason='gone')
        with self.assertRaises(ValueError):
            service.restore(self.db, 'snapshot:usa_beef', 2)


class ProductSourceTests(HistoryTestCase):
    def make_source(self):
        source = models.ProductSource(id='s1', country_name='Jamaica', name='MOA', url='https://example.test/prices', status='ok', product_count=0, created_at='2026-01-01')
        self.db.add(source)
        self.db.commit()
        return source

    def test_a_site_read_that_shrinks_is_held_and_the_source_keeps_its_products(self):
        source = self.make_source()
        with mock.patch.object(product_sources, 'analyze_url', return_value=(products(20), 'first')):
            product_sources._analyze(self.db, source)
            self.db.commit()
        self.assertEqual(source.product_count, 20)
        with mock.patch.object(product_sources, 'analyze_url', return_value=(products(3), 'second')):
            outcome = product_sources._analyze(self.db, source)
            self.db.commit()
        self.assertEqual(outcome, 'held')
        self.assertEqual(source.product_count, 20)
        self.assertIn('held for approval', source.status_message)
        self.assertEqual(len(self.live('custom_s1')), 20)
        held = store.held_updates()[0]
        service.approve(self.db, held['id'])
        self.assertEqual(len(self.live('custom_s1')), 3)
        self.assertEqual(self.db.get(models.ProductSource, 's1').product_count, 3)

    def test_a_file_loaded_by_a_person_is_not_held(self):
        source = self.make_source()
        product_sources._store(self.db, source, products(20), 'file', 'one')
        product_sources._store(self.db, source, products(2), 'file', 'two')
        self.assertEqual(store.held_updates(), [])
        self.assertEqual(len(self.live('custom_s1')), 2)

    def test_a_deleted_source_can_be_restored_with_its_settings(self):
        source = self.make_source()
        product_sources._store(self.db, source, products(15), 'site', 'read')
        self.db.commit()
        product_sources.delete_product_source('s1', self.db)
        self.assertIsNone(self.db.get(models.ProductSource, 's1'))
        self.assertEqual(store.latest('snapshot:custom_s1')['kind'], 'deleted')
        service.restore(self.db, 'snapshot:custom_s1', 1)
        row = self.db.get(models.ProductSource, 's1')
        self.assertEqual((row.name, row.country_name, row.product_count), ('MOA', 'Jamaica', 15))
        self.assertEqual(len(self.live('custom_s1')), 15)


class BuiltInEndpointTests(HistoryTestCase):
    def test_a_built_in_fetch_that_comes_back_empty_answers_409_and_keeps_the_data(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        handler = usa_sourcing._endpoint('usa_beef', lambda: [], 'Beef')
        with self.assertRaises(HTTPException) as caught:
            handler(db=self.db)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn('held for approval', caught.exception.detail)
        self.assertEqual(len(self.live('usa_beef')), 20)


class MarketSizeTests(HistoryTestCase):
    def data(self, rows):
        return {'categories': [{'chapter': f'{i:02d}', 'value': 100.0} for i in range(rows)]}

    def test_a_partial_recompute_is_held_and_restore_keeps_the_original_date(self):
        first = market_size_store.save_snapshot(self.db, 'tam', 'M', ['01'], self.data(12))
        with self.assertRaises(HeldForApproval) as caught:
            market_size_store.save_snapshot(self.db, 'tam', 'M', ['01'], self.data(5), guard=True)
        self.assertEqual(market_size_store.get_snapshot(self.db, 'tam')['computed_at'], first['computed_at'])
        market_size_store.save_snapshot(self.db, 'tam', 'M', ['01'], self.data(12), force=True)  # a later healthy run, different stamp
        service.approve(self.db, caught.exception.held_id) if store.get_held(caught.exception.held_id)['status'] == 'pending' else None
        service.restore(self.db, 'market_size:tam', 1)
        restored = market_size_store.get_snapshot(self.db, 'tam')
        self.assertEqual(restored['computed_at'], first['computed_at'])
        self.assertEqual(len(restored['data']['categories']), 12)


class FileTests(HistoryTestCase):
    def test_file_versions_restore_and_calculators_reload(self):
        backend = Path(self.tmp.name) / 'backend'
        target = backend / 'country_profiles' / 'c1.md'
        target.parent.mkdir(parents=True)
        with mock.patch.object(service, 'BACKEND', backend.resolve()):
            target.write_text('first', encoding='utf-8')
            service.record_file(target, 'built')
            target.write_text('second', encoding='utf-8')
            service.record_file(target, 'built again')
            self.assertIsNone(service.record_file(target, 'unchanged'))
            self.assertEqual(len(store.versions('file:country_profiles/c1.md')), 2)
            service.restore(self.db, 'file:country_profiles/c1.md', 1)
            self.assertEqual(target.read_text(encoding='utf-8'), 'first')
            self.assertEqual(len(store.versions('file:country_profiles/c1.md')), 3)

    def test_restore_refuses_a_path_outside_the_app(self):
        backend = Path(self.tmp.name) / 'backend'
        backend.mkdir()
        store.record('file:../outside.txt', 'file', b'x', reason='t')
        with mock.patch.object(service, 'BACKEND', backend.resolve()):
            with self.assertRaises(ValueError):
                service.restore(self.db, 'file:../outside.txt', 1)


class BaselineTests(HistoryTestCase):
    def test_baseline_records_today_then_only_what_changed_outside_the_hooks(self):
        self.db.add(models.PriceComparisonSnapshot(source='usa_eggs', data_json=json.dumps(products(4)), fetched_at='2026-11-09'))
        self.db.add(models.PriceComparisonSnapshot(source='comtrade_categories_M_1_2025', data_json='[]', fetched_at='2026-11-09'))
        self.db.commit()
        with mock.patch.object(service, 'tracked_files', return_value=[]):
            first = service.baseline(self.db)
            self.assertEqual(first['added'], ['snapshot:usa_eggs'])
            self.assertEqual(store.latest('snapshot:usa_eggs')['reason'], 'baseline')
            self.assertEqual(service.baseline(self.db), {'added': [], 'unchanged': 1})
            self.db.query(models.PriceComparisonSnapshot).filter_by(source='usa_eggs').one().data_json = json.dumps(products(5))
            self.db.commit()
            again = service.baseline(self.db)
        self.assertEqual(again['added'], ['snapshot:usa_eggs'])
        self.assertIn('outside', store.latest('snapshot:usa_eggs')['reason'])


class ApiTests(HistoryTestCase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(history_router.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def test_datasets_log_diff_held_approve_restore(self):
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(20))
        snapshot_store.save_snapshot(self.db, 'usa_beef', products(24, 2.0))
        datasets = self.client.get('/api/data-history/datasets').json()
        self.assertEqual((datasets[0]['scope'], datasets[0]['version'], datasets[0]['versions']), ('snapshot:usa_beef', 2, 2))
        self.assertIn('USDA', datasets[0]['label'])
        self.assertEqual(len(self.client.get('/api/data-history/log', params={'scope': 'snapshot:usa_beef'}).json()), 2)
        diff = self.client.get('/api/data-history/diff', params={'scope': 'snapshot:usa_beef'}).json()
        self.assertEqual((diff['from'], diff['to'], diff['added'], diff['price_changed']), (1, 2, 4, 20))
        with self.assertRaises(HeldForApproval) as caught:
            snapshot_store.save_snapshot(self.db, 'usa_beef', [], guard=True)
        held = self.client.get('/api/data-history/held').json()
        self.assertEqual((len(held), held[0]['compare']['new_count']), (1, 0))
        self.assertEqual(self.client.post(f'/api/data-history/held/{caught.exception.held_id}/reject').json()['status'], 'rejected')
        self.assertEqual(self.client.post(f'/api/data-history/held/{caught.exception.held_id}/reject').status_code, 409)
        restored = self.client.post('/api/data-history/restore', json={'scope': 'snapshot:usa_beef', 'version': 1}).json()
        self.assertEqual(restored['products'], 20)
        self.assertEqual(self.client.post('/api/data-history/restore', json={'scope': 'snapshot:usa_beef', 'version': 99}).status_code, 404)
        self.assertEqual(self.client.get('/api/data-history/diff', params={'scope': 'snapshot:none'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
