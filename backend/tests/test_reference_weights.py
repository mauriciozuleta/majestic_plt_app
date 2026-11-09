import unittest

from backend.catalog_normalization.reference import lookup
from backend.catalog_normalization.service import items_in_weight, normalize_price
from backend.catalog_normalization.store import MemoryStore


class ReferenceWeightTests(unittest.TestCase):
    def test_a_fruit_is_corrected_from_its_edible_weight_to_the_weight_as_bought(self):
        pineapple = lookup('Pineapples')
        self.assertAlmostEqual(pineapple.item_kg, 0.905 / (1 - 0.49), places=3)  # 905 g edible, refuse 49%
        self.assertAlmostEqual(pineapple.item_kg_min, 0.905)
        self.assertIn('USDA SR28 #09266', pineapple.note)

    def test_a_head_is_taken_as_sold(self):
        self.assertAlmostEqual(lookup('Cauliflower').item_kg, 0.588)
        self.assertAlmostEqual(lookup('Lettuce').item_kg, 0.539)
        self.assertAlmostEqual(lookup('Broccoli', 'bunch').item_kg, 0.608)

    def test_words_in_parentheses_are_kept(self):
        self.assertIsNotNone(lookup('Peppers (Bell Type)'))

    def test_no_rule_no_answer_and_look_alikes_are_excluded(self):
        for name in ('Lulo (Naranjilla)', 'Tree Tomato (Tamarillo)', 'Cilantro', 'Banana Passionfruit (Boyaca variety)', 'Granadilla (Sweet Passion Fruit)', 'Apples, Processed'):
            self.assertIsNone(lookup(name), name)
        self.assertIsNone(lookup('Pineapple', 'bunch'))  # a rule answers only its own unit

    def test_colombian_names_are_covered(self):
        for name in ('Gold Pineapple', 'Tommy Atkins Mango', 'Creole Banana', 'Harton Plantain', 'Cassava / Yuca (Armenia grade)', 'Maradol Papaya', 'Hawaiian Papaya', 'Passion Fruit (yellow)'):
            self.assertIsNotNone(lookup(name), name)
        self.assertLess(lookup('Hawaiian Papaya').item_kg, lookup('Maradol Papaya').item_kg)

    def test_the_conversion_uses_it_before_anything_researched(self):
        result = normalize_price('Pineapples', 'each', 3.23, MemoryStore())
        self.assertEqual(result.method, 'reference_item_weight')
        self.assertAlmostEqual(result.price_per_kg, 3.23 / (0.905 / 0.51), places=3)
        self.assertIn('USDA', result.sources[0] if 'USDA' in result.sources[0] else result.note)

    def test_a_count_pack_multiplies_it(self):
        result = normalize_price('Peppers (Bell Type)', '3 count filmbag', 3.40, MemoryStore())
        self.assertEqual(result.method, 'reference_item_weight')
        self.assertAlmostEqual(result.pack_weight_kg, 3 * 0.119 / 0.82, places=3)

    def test_both_directions_without_any_research(self):
        self.assertAlmostEqual(items_in_weight('Mangoes', 10, MemoryStore())['items'], 10 / (0.336 / 0.71), places=2)


if __name__ == '__main__':
    unittest.main()
