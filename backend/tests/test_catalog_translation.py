import json
import re
import unittest
from pathlib import Path

from backend.catalog_normalization.catalog import annotate, fields_for
from backend.catalog_normalization.store import ItemWeight, MemoryStore
from backend.catalog_normalization.translate import DATA_FILE, normalize_name, translate_name

ROOT = Path(__file__).resolve().parents[2]


class TranslateTests(unittest.TestCase):
    def test_normalization_matches_the_frontends(self):
        self.assertEqual(normalize_name('  Piña  Gold (Kilo) '), 'pina gold')
        self.assertEqual(normalize_name('PLÁTANO Harton'), 'platano harton')

    def test_dictionary_entry(self):
        result = translate_name('Acelga')
        self.assertEqual((result.text, result.translated, result.tier), ('Swiss Chard', True, 'dictionary'))

    def test_an_override_wins_over_the_dictionary(self):
        result = translate_name('Acelga', {'acelga': 'Chard'})
        self.assertEqual((result.text, result.tier), ('Chard', 'override'))

    def test_fuzzy_match_of_a_variant(self):
        result = translate_name('Brocolli')  # a typo of the dictionary key 'brocoli'
        self.assertTrue(result.translated)
        self.assertEqual(result.tier, 'fuzzy')

    def test_unknown_name_stays_spanish_and_is_flagged(self):
        result = translate_name('Zzzxq')
        self.assertEqual((result.text, result.translated, result.tier), ('Zzzxq', False, 'none'))

    def test_the_frontend_uses_the_same_dictionary_file(self):
        source = (ROOT / 'src/components/company/tabs/OperationsTab/MarketAnalysis/productTranslations.js').read_text(encoding='utf-8')
        self.assertIn('product_translations_es_en.json', source)
        self.assertGreater(len(json.loads(DATA_FILE.read_text(encoding='utf-8'))), 250)
        self.assertIsNone(re.search(r"^\s*acelga: 'Swiss Chard'", source, re.MULTILINE))  # no second copy left in the JS file


class CatalogUsesEnglishNames(unittest.TestCase):
    def test_a_colombian_product_is_read_under_its_english_name(self):
        product = {'id': 'pina gold', 'category': 'frutas', 'nameEs': 'Acelga', 'unit': 'other', 'unitLabel': 'unidad', 'price': 3000}
        name, unit, _price = fields_for('corabastos', product)
        self.assertEqual(name, 'Swiss Chard')
        store = MemoryStore()
        store.put(ItemWeight('Swiss Chard', 'each', 0.5, confidence='medium', note='test'))
        annotate('corabastos', [product], store)
        self.assertAlmostEqual(product['norm']['price_per_kg'], 6000.0)
        self.assertEqual((product['norm']['name_en'], product['norm']['translation']), ('Swiss Chard', 'dictionary'))


if __name__ == '__main__':
    unittest.main()


class CorabastosPackagesTests(unittest.TestCase):
    def convert(self, name_es, label, price):
        product = {'id': 'x', 'category': 'frutas', 'nameEs': name_es, 'unit': 'other', 'unitLabel': label, 'price': price}
        annotate('corabastos', [product], MemoryStore())
        return product['norm']

    def test_a_box_of_fruit_is_priced_per_kg(self):
        norm = self.convert('Mango Tommy', 'CAJA (11 per package)', 9091.0)
        self.assertEqual(norm['method'], 'stated_weight')
        self.assertAlmostEqual(norm['price_per_kg'], 9091.0)
        self.assertIn('already per kg', norm['note'])

    def test_bags_and_baskets_too(self):
        self.assertAlmostEqual(self.convert('Yuca Armenia', 'BOLSA (30 per package)', 2500.0)['price_per_kg'], 2500.0)
        self.assertAlmostEqual(self.convert('Lulo', 'CANASTILLA (25 per package)', 4800.0)['price_per_kg'], 4800.0)

    def test_a_bunch_or_dozen_stays_a_count_unit(self):
        self.assertEqual(self.convert('Cilantro', 'ATADO (10 per package)', 9000.0)['method'], 'needs_research')
        self.assertEqual(self.convert('Lulo', 'DOCENA (12 per package)', 5833.0)['method'], 'needs_research')
        self.assertEqual(self.convert('Coco', 'DOCENA (12 per package)', 5833.0)['method'], 'reference_item_weight')  # a coconut has a USDA weight

    def test_a_pack_of_unidades_is_the_price_of_the_whole_pack(self):
        self.assertEqual(self.convert('Huevo', '30 UNIDADES (1 per package)', 14000.0)['method'], 'official_factor')


class PricedUnitTests(unittest.TestCase):
    def test_a_whole_pack_weight_keyed_by_the_exact_name(self):
        from backend.catalog_normalization.service import normalize_price
        from backend.catalog_normalization.store import PRICED_UNIT

        store = MemoryStore()
        store.put(ItemWeight('Pimento (S)', PRICED_UNIT, 4.5, confidence='low', note='legacy'))
        result = normalize_price('Pimento (S)', "100's", 900.0, store)
        self.assertEqual(result.method, 'researched_item_weight')
        self.assertAlmostEqual(result.price_per_kg, 200.0)
        self.assertEqual(normalize_price('Pimento (L)', "100's", 900.0, store).method, 'needs_research')  # another pack, not the same row
