"""The Market Analysis status columns, worked out on the server: profile, analyses, products still lacking a weight or an HS code, and whether a country has product data."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base
from backend.portfolio import status
from backend.snapshot_store import save_snapshot

NOW = '2026-11-10T00:00:00+00:00'


class MarketAnalysisStatusTests(unittest.TestCase):
    def setUp(self):
        database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(database)
        self.db = sessionmaker(bind=database)()
        self.addCleanup(self.db.close)
        self.db.add_all([
            models.CommercialRegion(id='r1', company_id='c1', name='Caribbean'),
            models.CommercialCountry(id='co', company_id='c1', region_id='r1', name='Colombia', country_code='CO'),
            models.CommercialCountry(id='jm', company_id='c1', region_id='r1', name='Jamaica', country_code='JM'),
            models.CommercialCountry(id='bs', company_id='c1', region_id='r1', name='Bahamas', country_code='BS'),
        ])
        self.db.commit()

    def run_status(self, profiles=None, analyses=None, missing=None, hs=None):
        profiles, analyses = profiles or [], analyses or []
        with mock.patch('backend.routers.country_profile.list_country_profiles', lambda company_id, db: profiles), \
                mock.patch('backend.routers.competitiveness.list_competitiveness_analyses', lambda company_id, db: analyses), \
                mock.patch('backend.routers.catalog_normalization.missing_summary', lambda db: {'countries': missing or {}}), \
                mock.patch.object(status.hs_store, 'status', lambda db: {'countries': hs or {}}):
            return status.market_analysis_status(self.db)

    def test_every_country_gets_an_entry_with_its_counts(self):
        result = self.run_status(profiles=[{'country_id': 'jm', 'country_name': 'Jamaica', 'generated_at': NOW}],
                                 missing={'Colombia': 5}, hs={'Colombia': {'no_code': 1, 'heading_only': 11}, 'Jamaica': {'no_code': 2}})
        self.assertEqual(set(result), {'co', 'jm', 'bs'})
        self.assertEqual(result['jm']['profile']['generated_at'], NOW)
        self.assertIsNone(result['co']['profile'])
        self.assertEqual((result['co']['missingCount'], result['co']['hsMissingCount']), (5, 12))
        self.assertEqual((result['jm']['missingCount'], result['jm']['hsMissingCount']), (0, 2))

    def test_an_analysis_counts_for_its_target_and_for_its_source_by_name(self):
        row = {'target_country_id': 'jm', 'target_country_name': 'Jamaica', 'source_country_name': ' colombia ', 'generated_at': NOW}
        result = self.run_status(analyses=[row])
        self.assertEqual([len(result[key]['analyses']) for key in ('co', 'jm', 'bs')], [1, 1, 0])

    def test_product_data_comes_from_the_stored_catalogs(self):
        self.assertFalse(any(entry['hasProductData'] for entry in self.run_status().values()))
        save_snapshot(self.db, 'la_mayorista', [{'id': 'x', 'nameEs': 'Acelga'}])
        self.db.add(models.ProductSource(id='ps', country_name='Jamaica', name='Own', status='ok', product_count=1, created_at=NOW))
        self.db.commit()
        save_snapshot(self.db, 'custom_ps', [{'id': 'y'}])
        result = self.run_status()
        self.assertEqual([result[key]['hasProductData'] for key in ('co', 'jm', 'bs')], [True, True, False])


if __name__ == '__main__':
    unittest.main()
