import unittest
from unittest import mock

from backend.catalog_normalization.catalog import annotate
from backend.catalog_normalization.store import ItemWeight, MemoryStore
from backend.usa_sources import retail_produce


def _row(commodity, size, price, stores, region='National', organic='No', community='Fruit', week='10/31/2026', variety='N/A'):
    return {'commodity': commodity, 'variety': variety, 'size': size, 'wtd_avg_price': price, 'store_count': stores, 'region': region, 'organic': organic,
            'community': community, 'report_begin_date': week, 'report_end_date': '11/06/2026'}


class RetailProduceTests(unittest.TestCase):
    def fetch(self, rows):
        with mock.patch.object(retail_produce, 'fetch_report', return_value={'Report Header': [{'x': 1}], 'Report Details': rows}):
            return retail_produce.fetch_retail_produce_products()

    def test_keeps_only_the_latest_week_national_conventional_fruit_and_vegetables(self):
        rows = [_row('Bananas', 'per lb', 0.61, 387), _row('Bananas', 'per lb', 0.8, 693, organic='Yes'), _row('Bananas', 'per lb', 0.7, 50, region='Northeast'),
                _row('Bananas', 'per lb', 0.5, 387, week='10/24/2026'), _row('Honey', '12 oz', 6.4, 700, community='Other Specialty Crop Items'),
                _row('Apples, Processed', '64 oz', 2.79, 1744), _row('Carrots', '1 lb bag', 1.27, 3853, community='Vegetables')]
        products = self.fetch(rows)
        self.assertEqual(sorted(p['commodity'] for p in products), ['Bananas', 'Carrots'])
        self.assertTrue(all(p['detail'] and p['unit'].startswith('USD/') for p in products))

    def test_consolidated_row_is_the_store_weighted_average_per_kg(self):
        rows = [_row('Apples', '3 lb bag', 3.0, 100, variety='GALA'), _row('Apples', 'per lb', 1.5, 300, variety='FUJI')]
        products = annotate('usa_retail_produce', self.fetch(rows), MemoryStore())
        consolidated = [p for p in products if p.get('consolidated')]
        self.assertEqual(len(consolidated), 1)
        per_kg_bag, per_kg_lb = 3.0 / (3 * 0.45359237), 1.5 / 0.45359237
        expected = (100 * per_kg_bag + 300 * per_kg_lb) / 400
        self.assertAlmostEqual(consolidated[0]['price'], expected, places=3)
        self.assertEqual(consolidated[0]['unit'], 'USD/kg')
        self.assertEqual(consolidated[0]['pack_rows'], 2)
        self.assertAlmostEqual(consolidated[0]['norm']['price_per_kg'], expected, places=3)  # the consolidated row is itself normalized (a stated kg)

    def test_a_count_pack_joins_the_average_only_once_its_item_weight_is_known(self):
        rows = [_row('Lulo', '4 count mesh bags', 3.45, 850), _row('Lulo', 'each', 1.0, 150)]
        store = MemoryStore()
        products = annotate('usa_retail_produce', self.fetch(rows), store)
        self.assertEqual([p for p in products if p.get('consolidated')], [])  # nothing convertible yet: no average row
        store.put(ItemWeight('Lulo', 'each', 0.2, confidence='medium', note='test'))
        products = annotate('usa_retail_produce', products, store)  # re-annotating rebuilds the consolidated rows from the detail rows
        consolidated = [p for p in products if p.get('consolidated')]
        self.assertEqual(len(consolidated), 1)
        expected = (850 * (3.45 / 0.8) + 150 * (1.0 / 0.2)) / 1000
        self.assertAlmostEqual(consolidated[0]['price'], expected, places=3)
        self.assertEqual(len([p for p in products if p.get('detail')]), 2)  # the packs are kept, not duplicated


if __name__ == '__main__':
    unittest.main()
