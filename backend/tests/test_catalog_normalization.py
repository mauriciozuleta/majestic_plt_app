import unittest

from backend.catalog_normalization import ItemWeight, MemoryStore, items_in_weight, normalize_catalog, normalize_price, parse_unit, weight_of_items
from backend.catalog_normalization.units import LB_TO_KG, OZ_TO_KG


class ParseUnitTests(unittest.TestCase):
    def weight(self, unit, name=''):
        parsed = parse_unit(unit, name)
        self.assertEqual(parsed.kind, 'weight', (unit, parsed))
        return parsed.weight_kg

    def test_weights_as_written(self):
        self.assertAlmostEqual(self.weight('per lb', 'Bananas'), LB_TO_KG)
        self.assertAlmostEqual(self.weight('3 lb bag', 'Apples'), 3 * LB_TO_KG)
        self.assertAlmostEqual(self.weight('12 oz bag', 'Beans'), 12 * OZ_TO_KG)
        self.assertAlmostEqual(self.weight('1 pint (11-12 oz cntr w/ lid)', 'Blueberries'), 11.5 * OZ_TO_KG)  # a range is averaged
        self.assertAlmostEqual(self.weight('flats 8 1-lb containers with lids', 'Strawberries'), 8 * LB_TO_KG)
        self.assertAlmostEqual(self.weight('6 x 500 g', 'Rice'), 3.0)
        self.assertAlmostEqual(self.weight('25 lb cartons loose', 'Tomatoes'), 25 * LB_TO_KG)
        self.assertAlmostEqual(self.weight('USD/cwt (100lb)', 'Beef'), 100 * LB_TO_KG)
        self.assertAlmostEqual(self.weight('bulto de 50 kilos', 'Papa'), 50.0)
        self.assertAlmostEqual(self.weight('45kg bag', 'Rice'), 45.0)
        self.assertAlmostEqual(self.weight('libra', 'Papa'), LB_TO_KG)
        self.assertAlmostEqual(self.weight('arroba', 'Panela'), 25 * LB_TO_KG)

    def test_bare_unit_uses_the_pack_weight_in_the_name(self):
        self.assertAlmostEqual(self.weight('g', 'Picsweet Green Peas 340G'), 0.34)
        self.assertAlmostEqual(self.weight('kg', 'Imported Apple Red Bag Prepacked 1.4KG'), 1.4)
        self.assertAlmostEqual(self.weight('kg', 'Acelga'), 1.0)
        self.assertAlmostEqual(self.weight('', 'Green Peas 340G'), 0.34)

    def test_counts(self):
        cases = [('each', 1.0, 'each'), ('per bunch', None, 'bunch'), ('4 count mesh bags', 4.0, 'pack'), ('per sleeve', None, 'sleeve'), ('dozen', 12.0, 'dozen'),
                 ("100's", 100.0, 'pack'), ('box of 18', 18.0, 'pack'), ('3 count filmbag', 3.0, 'pack'), ('1 head', 1.0, 'head')]
        for unit, count, count_unit in cases:
            parsed = parse_unit(unit, 'Something')
            self.assertEqual((parsed.kind, parsed.item_count, parsed.count_unit), ('count', count, count_unit), unit)

    def test_volume_and_unknown(self):
        self.assertEqual(parse_unit('64 oz (1/2 gallon)', 'Apple Juice').kind, 'volume')
        self.assertEqual(parse_unit('1 liter', 'Milk').kind, 'volume')
        self.assertEqual(parse_unit('6 inch pot', 'Chrysanthemums').kind, 'unknown')
        self.assertEqual(parse_unit(None, 'x').kind, 'unknown')


class NormalizeTests(unittest.TestCase):
    def store(self):
        store = MemoryStore()
        store.put(ItemWeight('pineapple', 'each', 1.5, 1.2, 2.0, std_pack_kg=9.0, std_pack_items=6, confidence='high', note='USDA', sources=['https://x']))
        store.put(ItemWeight('avocado', 'each', 0.2, 0.15, 0.3, confidence='medium', note='Hass'))
        store.put(ItemWeight('cilantro', 'bunch', 0.07, confidence='medium', note='retail bunch'))
        return store

    def test_a_stated_weight_needs_no_research(self):
        result = normalize_price('Apples', '3 lb bag', 4.0, MemoryStore())
        self.assertEqual(result.method, 'stated_weight')
        self.assertAlmostEqual(result.price_per_kg, 4.0 / (3 * LB_TO_KG))

    def test_price_per_each_uses_the_researched_item_weight(self):
        result = normalize_price('Pineapple', 'each', 3.0, self.store())
        self.assertEqual(result.method, 'researched_item_weight')
        self.assertAlmostEqual(result.price_per_kg, 2.0)  # 3.00 per 1.5 kg

    def test_an_unresearched_product_says_it_needs_research(self):
        result = normalize_price('Mango', 'each', 3.0, self.store())
        self.assertEqual(result.method, 'needs_research')
        self.assertIsNone(result.price_per_kg)

    def test_a_count_pack_multiplies_the_item_weight(self):
        result = normalize_price('Avocado', '4 count mesh bags', 3.6, self.store())
        self.assertAlmostEqual(result.pack_weight_kg, 0.8)
        self.assertAlmostEqual(result.price_per_kg, 4.5)
        self.assertAlmostEqual(result.price_per_item, 0.9)

    def test_bunch_uses_the_weight_of_a_bunch(self):
        result = normalize_price('Cilantro', 'per bunch', 0.74, self.store())
        self.assertAlmostEqual(result.price_per_kg, 0.74 / 0.07)

    def test_eggs_use_the_official_usda_dozen_weight(self):
        result = normalize_price('Eggs, Extra Large', 'dozen', 3.0, MemoryStore())
        self.assertEqual(result.method, 'official_factor')
        self.assertAlmostEqual(result.price_per_kg, 3.0 / (27 * OZ_TO_KG))

    def test_grain_bushels_use_the_official_test_weight(self):
        result = normalize_price('US #2 Yellow Corn', 'USD/bushel', 5.35, MemoryStore())
        self.assertAlmostEqual(result.price_per_kg, 5.35 / (56 * LB_TO_KG))

    def test_both_directions(self):
        store = self.store()
        self.assertAlmostEqual(items_in_weight('avocado', 10, store)['items'], 50)
        self.assertAlmostEqual(weight_of_items('pineapple', 8, store)['weight_kg'], 12.0)
        self.assertIsNone(items_in_weight('mango', 10, store))

    def test_catalog_researches_each_missing_product_once_and_converts_every_row(self):
        calls = []

        def research(batch):
            calls.append(batch)
            return [ItemWeight(name, unit, 0.5, confidence='medium', note='test') for name, unit, _ in batch]

        rows = [{'name': 'Papaya', 'unit': 'each', 'price': 2.0}, {'name': 'Papaya', 'unit': 'each', 'price': 3.0}, {'name': 'Rice', 'unit': '5 lb bag', 'price': 4.0}]
        out = normalize_catalog(rows, MemoryStore(), research=research)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 1)  # one distinct product researched, not two
        self.assertAlmostEqual(out[0]['normalized']['price_per_kg'], 4.0)
        self.assertAlmostEqual(out[1]['normalized']['price_per_kg'], 6.0)
        self.assertEqual(out[2]['normalized']['method'], 'stated_weight')

    def test_without_research_a_count_row_says_it_needs_it(self):
        out = normalize_catalog([{'name': 'Papaya', 'unit': 'each', 'price': 2.0}], MemoryStore(), allow_research=False)
        self.assertEqual(out[0]['normalized']['method'], 'needs_research')
        self.assertIsNone(out[0]['normalized']['price_per_kg'])


if __name__ == '__main__':
    unittest.main()
