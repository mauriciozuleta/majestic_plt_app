import unittest

from backend import tax_calc
from backend.tax_calc import Inputs, mapping
from backend.tax_calc.usa import _rate_parts


def _by_name(result):
    return {tax['name']: tax['amount'] for tax in result['taxes']}


class JamaicaTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Jamaica')
        if not self.calculator.info()['ready']:
            self.skipTest('Jamaica tariff data not present (backend/documents/tax_data/Jamaica/tariff.csv)')

    def test_fresh_tomatoes_from_colombia(self):
        # tariff line 0702000000: duty 100%, additional stamp duty 80%, SCF 0.3%, environmental levy 0.85%, GCT 15% on CIF + duties
        result = self.calculator.calculate('0702000000', Inputs(goods_value_usd=1510, quantity_kg=1000, origin='Colombia')).to_dict()
        amounts = _by_name(result)
        self.assertAlmostEqual(amounts['Import duty'], 1510.0)
        self.assertAlmostEqual(amounts['Additional stamp duty'], 1208.0)
        self.assertAlmostEqual(amounts['General consumption tax (GCT)'], (1510 + 1510 + 1208) * 0.15)
        self.assertAlmostEqual(result['total_tax_usd'], 3369.57, places=2)
        self.assertAlmostEqual(result['total_per_kg_usd'], 3.3696, places=4)
        self.assertTrue(result['complete'])

    def test_freight_and_insurance_enter_the_cif_value(self):
        result = self.calculator.calculate('0702000000', Inputs(goods_value_usd=1000, freight_usd=200, insurance_usd=50)).to_dict()
        self.assertAlmostEqual(result['value_basis']['amount_usd'], 1250.0)
        self.assertAlmostEqual(_by_name(result)['Import duty'], 1250.0)

    def test_caricom_origin_waives_import_duty_and_advance_gct_is_not_counted(self):
        result = self.calculator.calculate('0702000000', Inputs(goods_value_usd=1000, origin='Trinidad and Tobago', commercial_importer=True)).to_dict()
        amounts = _by_name(result)
        self.assertEqual(amounts['Import duty'], 0.0)
        advance = next(tax for tax in result['taxes'] if tax['recoverable'])
        self.assertGreater(advance['amount'], 0)
        self.assertAlmostEqual(result['total_tax_usd'], round(sum(tax['amount'] for tax in result['taxes'] if not tax['recoverable']), 2))

    def test_search_finds_the_line_by_word_and_by_code(self):
        self.assertIn('0702000000', [line['code'] for line in self.calculator.search('tomatoes')])
        self.assertEqual(self.calculator.search('0702000000')[0]['code'], '0702000000')


class UsaTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('United States')
        if not self.calculator.info()['ready']:
            self.skipTest('US HTS data not present (backend/documents/tax_data/United States/hts_full.json)')

    def test_rate_parser(self):
        self.assertEqual(_rate_parts('Free'), ([], True))
        self.assertEqual(_rate_parts('6.4%'), ([{'type': 'adv', 'pct': 6.4}], True))
        parts, understood = _rate_parts('2.5¢/kg + 5%')
        self.assertTrue(understood)
        self.assertEqual(parts, [{'type': 'spec', 'usd': 0.025, 'per': 'kg'}, {'type': 'adv', 'pct': 5.0}])
        self.assertFalse(_rate_parts('See heading 9903')[1])

    def test_tomatoes_from_china_pay_the_general_specific_rate(self):
        # 0702.00.20: 3.9¢/kg general; 2,000 kg -> 78.00; goods value above 2,500 -> merchandise processing fee at its minimum
        result = self.calculator.calculate('0702.00.20', Inputs(goods_value_usd=4000, quantity_kg=2000, origin='China')).to_dict()
        amounts = _by_name(result)
        self.assertAlmostEqual(amounts['Customs duty (specific)'], 78.0)
        self.assertAlmostEqual(amounts['Merchandise processing fee (MPF)'], 33.58)
        self.assertNotIn('Harbor maintenance fee (HMF)', amounts)  # air shipment

    def test_trade_agreement_origin_is_free_and_sea_adds_the_harbor_fee(self):
        result = self.calculator.calculate('0702.00.20', Inputs(goods_value_usd=5000, quantity_kg=2000, origin='Colombia', transport='sea')).to_dict()
        amounts = _by_name(result)
        self.assertEqual(amounts['Customs duty'], 0.0)
        self.assertAlmostEqual(amounts['Harbor maintenance fee (HMF)'], 6.25)

    def test_specific_duty_without_quantity_is_reported_not_guessed(self):
        result = self.calculator.calculate('0702.00.20', Inputs(goods_value_usd=1000, origin='China')).to_dict()
        self.assertFalse(result['complete'])
        self.assertTrue(any('quantity' in warning for warning in result['warnings']))


class MultiplierTests(unittest.TestCase):
    def setUp(self):
        self.jamaica = tax_calc.get('Jamaica')
        if not self.jamaica.info()['ready']:
            self.skipTest('Jamaica tariff data not present')

    def test_tomato_multiplier_matches_the_calculator(self):
        # Colombia -> Jamaica tomatoes at USD 1.51/kg: taxes are ~2.23 times the goods value
        computed = mapping.multiplier_for(self.jamaica, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 1.51}, 'Colombia')
        self.assertEqual(computed['status'], 'ok')
        self.assertEqual(computed['tariff_code'], '0702000000')
        self.assertAlmostEqual(computed['tax_multiplier'], 2.23, places=2)
        self.assertAlmostEqual(computed['landed_multiplier'], 3.23, places=2)

    def test_a_word_of_the_name_picks_among_lines_sharing_the_hs_code(self):
        computed = mapping.multiplier_for(self.jamaica, {'name': 'Chicken wings', 'hs_code': '020713', 'price_usd_kg': 3.0}, 'United States')
        self.assertEqual((computed['method'], computed['tariff_code']), ('hs+name', '0207130020'))

    def test_an_unnamed_product_falls_back_to_the_catch_all_and_is_flagged_for_review(self):
        computed = mapping.multiplier_for(self.jamaica, {'name': 'Chicken Frames', 'hs_code': '020713', 'price_usd_kg': 0.17}, 'United States')
        self.assertEqual((computed['method'], computed['status'], computed['tariff_code']), ('catch-all', 'review', '0207130090'))

    def test_a_product_without_hs_code_or_name_match_has_no_line(self):
        computed = mapping.multiplier_for(self.jamaica, {'name': 'Zzzz unknown thing', 'hs_code': None, 'price_usd_kg': 1.0}, 'Colombia')
        self.assertEqual(computed['status'], 'no_line')
        self.assertIsNone(computed.get('tax_multiplier'))

    def test_caricom_origin_lowers_the_multiplier(self):
        full = mapping.multiplier_for(self.jamaica, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 1.51}, 'Colombia')
        caricom = mapping.multiplier_for(self.jamaica, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 1.51}, 'Trinidad and Tobago')
        self.assertLess(caricom['tax_multiplier'], full['tax_multiplier'])


class UsaMultiplierTests(unittest.TestCase):
    def test_specific_duty_without_a_price_needs_the_price(self):
        usa = tax_calc.get('United States')
        if not usa.info()['ready']:
            self.skipTest('US HTS data not present')
        computed = mapping.multiplier_for(usa, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': None}, 'China')
        self.assertEqual(computed['status'], 'needs_price')
        self.assertIsNone(computed['tax_multiplier'])
        priced = mapping.multiplier_for(usa, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 2.0}, 'China')
        self.assertAlmostEqual(priced['tax_multiplier'], 0.039 / 2.0 * 1.0, places=3)  # 3.9 cents/kg on USD 2/kg goods (highest-of-3 lines)


if __name__ == '__main__':
    unittest.main()
