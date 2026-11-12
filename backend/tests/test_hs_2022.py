"""HS 2022 as the nomenclature in force, from the committed files (no network): a code of an older revision is refused / flagged; the US Census Schedule B (chapters 1-3, downloaded on
2026-11-12) has the same 6-digit codes as HS 2022, so it adds nothing at 6 digits."""

import json
import unittest
from pathlib import Path
from unittest import mock

from backend.catalog_normalization import hs, hs_store
from backend.comtrade import classification

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'schedule_b_chapters_01_03.json').read_text(encoding='utf-8'))


class BundledReferenceTests(unittest.TestCase):
    def test_the_files_are_committed_and_the_combined_one_is_a_superset(self):
        current, combined = classification.current_codes(), json.loads((classification.DATA_DIR / 'hs_combined.json').read_text(encoding='utf-8'))
        self.assertGreater(len(current), 6900)
        self.assertTrue(set(current) <= set(combined))
        old = [code for code in combined if len(code) == 6 and code not in current]
        self.assertGreater(len(old), 1000)  # codes of older revisions the combined file still holds (1,284 when built)

    def test_schedule_b_chapters_1_to_3_equal_hs_2022_exactly(self):
        for chapter, codes in FIXTURE['chapters'].items():
            ours = sorted(code for code in classification.current_codes() if len(code) == 6 and code.startswith(chapter))
            self.assertEqual(ours, codes, f'chapter {chapter}')

    def test_the_reference_is_read_from_the_committed_file_never_fetched(self):
        classification._reference = None
        self.addCleanup(setattr, classification, '_reference', None)
        with mock.patch.object(classification, '_fetch', side_effect=AssertionError('the network must not be used')):
            self.assertGreater(len(classification.reference_codes()), 8000)
            self.assertEqual(classification.hs_name('0201'), 'Meat of bovine animals; fresh or chilled')


class ObsoleteCodeTests(unittest.TestCase):
    def test_a_code_of_an_older_revision_is_refused_with_a_reason(self):
        for old in ('020710', '030419', '091040'):  # whole chicken, other fish fillets, thyme: HS 2002-2017 codes the old AI classifier chose
            with self.assertRaises(hs.HsError) as raised:
                hs.parse_code(old)
            self.assertIn('older HS revision', str(raised.exception))
        self.assertEqual(hs.parse_code('020711').hs6, '020711')  # its HS 2022 code
        self.assertEqual(hs.check('Jamaica', 'Whole Chicken', None, '020710')['status'], 'error')

    def test_a_stored_old_code_is_flagged_as_obsolete_in_the_product_block(self):
        index = hs.HsIndex({}, {'whole chicken': '020710', 'tomato': '070200'}, {'jamaica': 'JM'})
        old, fine = index.block('Jamaica', 'Whole Chicken'), index.block('Jamaica', 'Tomato')
        self.assertEqual((old['obsolete'], old['label'], old['code']), (True, 'obsolete', 'JM020710'))
        self.assertEqual((fine['obsolete'], fine['label']), (False, 'ok'))
        self.assertFalse(hs.is_obsolete('020100', 4))  # a padded heading is judged by its heading (0201 exists)

    def test_a_suggestion_with_an_old_code_is_dropped_not_offered(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend import models  # noqa: F401
        from backend.database import Base

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        self.addCleanup(db.close)
        with mock.patch.object(hs, 'suggest_from_rule', return_value={'code': '020710', 'method': 'rule', 'confidence': 'high', 'note': 'an old code'}):
            result = hs.suggest(db, [{'country': 'Jamaica', 'name': 'Whole Chicken'}])['results'][0]
        self.assertIsNone(result['suggestion'])
        self.assertEqual(result['validation']['status'], 'error')  # the reason is kept, so a person sees why nothing was offered
        self.assertIn('older HS revision', result['validation']['messages'][0])

    def test_the_ai_lists_only_hold_current_codes(self):
        listed = {entry['hs_code'] for entry in classification.list_searchable_hs_codes(current_only=True)}
        everything = {entry['hs_code'] for entry in classification.list_searchable_hs_codes()}
        self.assertNotIn('020710', listed)
        self.assertIn('020710', everything)
        self.assertIn('020711', listed)
        self.assertTrue(listed < everything)


class StartUpTests(unittest.TestCase):
    def test_catalogs_stored_before_the_obsolete_flag_are_rewritten_once(self):
        import json

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend import models
        from backend.database import Base
        from backend.catalog_normalization import hs_store

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        self.addCleanup(db.close)
        old = [{'id': '1', 'name': 'Whole Chicken', 'unit': 'kg', 'price': 5.0, 'hs': {'hs6': '020710', 'label': 'ok', 'status': 'suggested'}}]  # no `obsolete` key yet
        db.add(models.PriceComparisonSnapshot(source='custom_x', data_json=json.dumps(old), fetched_at='2026-11-10'))
        db.commit()
        self.assertGreater(hs_store.ensure_annotated(db), 0)
        self.assertEqual(hs_store.ensure_annotated(db), 0)  # once
        stored = json.loads(db.query(models.PriceComparisonSnapshot).one().data_json)
        self.assertIn('obsolete', stored[0]['hs'])


class StatusTests(unittest.TestCase):
    def test_an_old_code_counts_as_a_product_that_still_needs_an_hs_code(self):
        item = {'country': 'Jamaica', 'name': 'Whole Chicken', 'category': None, 'example': {}, 'hs': {'hs6': '020710', 'label': 'obsolete', 'obsolete': True, 'status': 'suggested'}}
        good = {'country': 'Jamaica', 'name': 'Tomato', 'category': None, 'example': {}, 'hs': {'hs6': '070200', 'label': 'ok', 'obsolete': False, 'status': 'suggested'}}
        with mock.patch.object(hs_store, 'catalog_products', return_value={('jamaica', 'a'): item, ('jamaica', 'b'): good}):
            status = hs_store.status(None)
        self.assertEqual(status['countries']['Jamaica'], {'obsolete': 1, 'suggested': 1})


class HeadingThatGainedSubheadingsTests(unittest.TestCase):
    def test_a_padded_heading_is_heading_only_not_an_old_code(self):
        code = hs.parse_code('100300')  # barley: 1003 still exists, it only gained 100310 / 100390
        self.assertEqual((code.hs6, code.level), ('100300', 4))
        self.assertFalse(hs.is_obsolete('100300', 4))
        with self.assertRaises(hs.HsError):
            hs.parse_code('020710')  # a real subheading that was split: still an old code

    def test_the_search_stays_inside_the_products_heading_and_skips_seed(self):
        self.assertEqual(hs.suggest_from_schedule_b('Barley', '1003')['code'], '100390')  # not 100310 (seed), not 110419 (rolled barley)
        self.assertIsNone(hs.suggest_from_schedule_b('Barley'))  # no heading known: three codes hold the word


class SaveOverOldCodeTests(unittest.TestCase):
    def test_a_person_can_save_the_current_code_over_a_stored_old_one(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend import models
        from backend.database import Base

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        self.addCleanup(db.close)
        db.add(models.ProductHsAssignment(country='Colombia', product_key=hs.hs_key('Whole Chicken'), hs_code='020710', hs_level=6, status='suggested', method='ai'))
        db.commit()
        result = hs_store.save_assignments(db, [{'country': 'Colombia', 'name': 'Whole Chicken', 'code': '020711'}])  # used to crash: the stored 020710 is not in HS 2022
        self.assertEqual((result['saved'], result['refused']), (1, []))
        row = db.get(models.ProductHsAssignment, ('Colombia', hs.hs_key('Whole Chicken')))
        self.assertEqual((row.hs_code, row.status), ('020711', 'corrected'))


if __name__ == '__main__':
    unittest.main()
