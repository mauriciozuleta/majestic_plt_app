"""The free table of retail pack sizes (backend/catalog_normalization/retail_unit.py, data/retail_unit_weights.json): the weight of a product priced per generic "unit" / "each" that is
really a pack or a bunch (a clamshell of raspberries, a bunch of cilantro). No AI, no network. It must outrank USDA's weight of one single piece for these commodities, never outrank a
weight a person typed or one researched for the bunch itself, and never answer for processed foods or counts of pieces."""

import unittest

from backend.catalog_normalization import retail_unit
from backend.catalog_normalization.service import normalize_price
from backend.catalog_normalization.store import ItemWeight, MemoryStore


class LookupTests(unittest.TestCase):
    def test_packs_and_bunches_of_fresh_produce(self):
        for name, unit, kg in [('Raspberries', 'each', 0.17), ('Strawberries', 'each', 0.454), ('Green Beans', 'each', 0.34), ('Asparagus', 'each', 0.45), ('Fresh Cilantro', 'bunch', 0.05),
                               ('Celery Stalk', 'each', 0.5), ('Spring Mix', 'each', 0.2), ('Baby Carrots', 'each', 0.45), ('Mushrooms Sliced', 'each', 0.227), ('Swiss Chard Rainbow', 'each', 0.4)]:
            found = retail_unit.lookup(name, unit)
            self.assertIsNotNone(found, name)
            self.assertAlmostEqual(found['kg'], kg, msg=name)

    def test_what_it_does_not_answer_for(self):
        self.assertIsNone(retail_unit.lookup('Pineapple', 'each'))  # produce sold by the piece: USDA's piece weight covers it
        self.assertIsNone(retail_unit.lookup('Cream Cheese Strawberry', 'each'))  # a cheese, whatever fruit is in the name
        self.assertIsNone(retail_unit.lookup('Strawberry Yogurt', 'each'))
        self.assertIsNone(retail_unit.lookup('Raspberries', 'each', 4))  # a count of several pieces is not one pack
        self.assertIsNone(retail_unit.lookup('Raspberries', 'dozen'))
        self.assertIsNone(retail_unit.lookup('Chicken Whole', 'each'))  # whole-chicken "unit" prices in these catalogs are per pound
        self.assertIsNone(retail_unit.lookup('', 'each'))

    def test_a_bracketed_variety_label_does_not_decide(self):
        self.assertIsNone(retail_unit.lookup('Apples (Raspberry Red)', 'each'))


class ConversionTests(unittest.TestCase):
    def test_raspberries_priced_per_unit_are_a_clamshell_not_one_berry(self):
        result = normalize_price('Raspberries', 'unit', 11.95, MemoryStore())
        self.assertEqual((result.method, result.confidence), ('retail_unit_weight', 'low'))
        self.assertAlmostEqual(result.pack_weight_kg, 0.17)
        self.assertAlmostEqual(result.price_per_kg, 11.95 / 0.17)  # about 70 per kg, not 2,987
        self.assertIn('6 oz clamshell', result.note)
        self.assertIn('low confidence', result.note)

    def test_it_outranks_the_weight_of_one_researched_piece_but_not_a_person(self):
        store = MemoryStore()
        store.put(ItemWeight('Raspberries', 'each', 0.004, confidence='medium', note='one berry'))  # the research of "one single whole item"
        self.assertEqual(normalize_price('Raspberries', 'unit', 11.95, store).method, 'retail_unit_weight')
        store.put(ItemWeight('Raspberries', 'each', 0.2, confidence='user', note='typed by a person'))
        typed = normalize_price('Raspberries', 'unit', 11.95, store)
        self.assertEqual((typed.method, typed.confidence), ('researched_item_weight', 'user'))
        self.assertAlmostEqual(typed.price_per_kg, 11.95 / 0.2)

    def test_a_weight_researched_for_the_bunch_itself_outranks_the_generic_table(self):
        store = MemoryStore()
        store.put(ItemWeight('Cilantro', 'bunch', 0.07, confidence='high', note='researched for a bunch'))
        result = normalize_price('Cilantro', 'per bunch', 5.0, store)
        self.assertEqual(result.method, 'researched_item_weight')
        self.assertAlmostEqual(result.pack_weight_kg, 0.07)
        self.assertEqual(normalize_price('Cilantro', 'per bunch', 5.0, MemoryStore()).method, 'retail_unit_weight')  # nothing researched: the table

    def test_a_weight_written_in_the_row_always_wins(self):
        result = normalize_price('Raspberries 6oz', 'unit', 11.99, MemoryStore())
        self.assertEqual(result.method, 'stated_weight')

    def test_a_count_of_pieces_and_a_piece_commodity_are_left_to_the_other_steps(self):
        self.assertNotEqual(normalize_price('Raspberries', '4 count', 11.95, MemoryStore()).method, 'retail_unit_weight')
        self.assertEqual(normalize_price('Pineapple', 'each', 5.0, MemoryStore()).method, 'reference_item_weight')  # USDA


if __name__ == '__main__':
    unittest.main()
