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


class TrinidadTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Trinidad and Tobago')
        if not self.calculator.info()['ready']:
            self.skipTest('Trinidad and Tobago tariff data not present (use "Update tariff data")')

    def test_fresh_tomatoes_pay_the_40_percent_cet_on_cif(self):
        result = self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, freight_usd=100, origin='Colombia')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Customs duty'], 440.0)  # 40% of 1,100 CIF
        self.assertAlmostEqual(result['total_tax_usd'], 440.0)  # VAT 12.5% is shown but recoverable
        vat = next(tax for tax in result['taxes'] if tax['name'].startswith('Value added'))
        self.assertTrue(vat['recoverable'])
        self.assertAlmostEqual(vat['amount'], (1100 + 440) * 0.125)

    def test_caricom_origin_is_duty_free(self):
        result = self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, origin='Jamaica')).to_dict()
        self.assertEqual(result['total_tax_usd'], 0.0)

    def test_search_by_code_and_by_name(self):
        self.assertEqual(self.calculator.search('0207.14.60', 1)[0]['code'], '0207.14.60')
        self.assertIn('0702.00.00', [row['code'] for row in self.calculator.search('tomatoes')])

    def test_unreadable_rate_is_reported_not_guessed(self):
        line = next((line for line in self.calculator.lines if line['status'] == 'unreadable'), None)
        if line is None:
            self.skipTest('every rate was readable')
        result = self.calculator.calculate(line['code'], Inputs(goods_value_usd=100)).to_dict()
        self.assertFalse(result['complete'])


class BahamasTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Bahamas')
        self.calculator.refresh()
        if not self.calculator.info()['ready']:
            self.skipTest('Bahamas tariff data not present (use "Update tariff data")')

    def test_fresh_tomatoes_pay_10_percent_and_warn_about_the_variable_rate(self):
        result = self.calculator.calculate('0702.0000', Inputs(goods_value_usd=1000, freight_usd=100, origin='Colombia')).to_dict()
        self.assertAlmostEqual(result['total_tax_usd'], 110.0)  # 10% of 1,100 CIF; VAT is shown but recoverable
        self.assertTrue(any('300%' in warning for warning in result['warnings']))

    def test_an_order_replaces_the_general_rate_but_not_above_the_ceiling(self):
        calculator = tax_calc.get('Bahamas')
        calculator.orders = {'0702.0000': {'rate': '60%', 'order': 'Test Order'}}
        try:
            self.assertAlmostEqual(calculator.calculate('0702.0000', Inputs(goods_value_usd=1000)).to_dict()['total_tax_usd'], 600.0)
            calculator.orders = {'0702.0000': {'rate': '400%'}}
            self.assertAlmostEqual(calculator.calculate('0702.0000', Inputs(goods_value_usd=1000)).to_dict()['total_tax_usd'], 100.0)
        finally:
            calculator.orders = {}

    def test_beer_pays_ad_valorem_plus_specific_per_gallon(self):
        result = self.calculator.calculate('2203.0010', Inputs(goods_value_usd=1000, quantity_units=100)).to_dict()
        self.assertAlmostEqual(result['total_tax_usd'], 100.0 + 1000.0)  # 10% + $10 BSD x 100 gallons

    def test_a_line_without_a_printed_rate_is_incomplete(self):
        result = self.calculator.calculate('2009.1900', Inputs(goods_value_usd=100)).to_dict()
        self.assertFalse(result['complete'])

    def test_no_caricom_waiver(self):
        self.assertAlmostEqual(self.calculator.calculate('0702.0000', Inputs(goods_value_usd=1000, origin='Jamaica')).to_dict()['total_tax_usd'], 100.0)


class SaintLuciaTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Saint Lucia')
        self.calculator.refresh()
        if not self.calculator.info()['ready']:
            self.skipTest('Saint Lucia tariff data not present (use "Update tariff data")')

    def test_fresh_tomatoes_pay_the_40_percent_cet_on_cif(self):
        result = self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, freight_usd=100, origin='Colombia')).to_dict()
        self.assertAlmostEqual(result['total_tax_usd'], 440.0)  # VAT 12.5% is shown but recoverable
        self.assertTrue(next(tax for tax in result['taxes'] if tax['name'].startswith('Value added'))['recoverable'])

    def test_caricom_origin_is_duty_free(self):
        self.assertEqual(self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, origin='Jamaica')).to_dict()['total_tax_usd'], 0.0)

    def test_specific_duty_per_100_kg_in_ec_dollars(self):
        result = self.calculator.calculate('0701.90.00', Inputs(goods_value_usd=1000, quantity_kg=1000)).to_dict()
        self.assertAlmostEqual(result['total_tax_usd'], 1000 / 100 * 1.65 / 2.70, places=2)

    def test_epa_excluded_line_keeps_the_cet_and_epa_free_line_is_free_for_eu_origin(self):
        self.assertAlmostEqual(self.calculator.calculate('0207.11.00', Inputs(goods_value_usd=1000, origin='Germany')).to_dict()['total_tax_usd'], 400.0)
        self.assertEqual(self.calculator.calculate('0306.11.00', Inputs(goods_value_usd=1000, origin='Germany')).to_dict()['total_tax_usd'], 0.0)

    def test_list_a_gives_saint_lucias_own_rate_not_the_cet_rate(self):
        line = self.calculator.by_code['0201.10.00']
        self.assertEqual((line['national_rate']['rate'], line['national_rate']['cet']), ('Free', '40%'))  # beef: CET 40%, Saint Lucia Free
        result = self.calculator.calculate('0201.10.00', Inputs(goods_value_usd=1000, origin='United States')).to_dict()
        self.assertEqual(result['total_tax_usd'], 0.0)
        self.assertTrue(any('Saint Lucia applies' in note for note in result['notes']))

    def test_every_parsed_national_rate_agrees_with_the_schedule(self):
        for code, national in self.calculator.national.items():
            line = self.calculator.by_code.get(code)
            if line and line['rate'] and line['rate'].endswith(('%', 'Free')) and national['rate'].endswith(('%', 'Free')):
                self.assertEqual(line['rate'], national['rate'], code)

    def test_a_line_in_an_unread_list_row_warns_that_the_rate_may_differ(self):
        code = next(line['code'] for line in self.calculator.lines if line['in_lists'])
        result = self.calculator.calculate(code, Inputs(goods_value_usd=1000, origin='United States')).to_dict()
        self.assertTrue(any('List D' in warning for warning in result['warnings']))


class GrenadaTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Grenada')
        self.calculator.refresh()
        if not self.calculator.info()['ready']:
            self.skipTest('Grenada tariff data not present (use "Update tariff data")')

    def test_fresh_tomatoes_pay_40_percent_on_cif_and_have_their_own_path(self):
        result = self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, freight_usd=100, origin='Colombia')).to_dict()
        self.assertAlmostEqual(result['total_tax_usd'], 440.0)  # VAT is shown but recoverable
        self.assertEqual(self.calculator.by_code['0702.00.00']['path'], 'Tomatoes, fresh or chilled.')

    def test_caricom_origin_is_duty_free(self):
        self.assertEqual(self.calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, origin='Jamaica')).to_dict()['total_tax_usd'], 0.0)

    def test_list_a_gives_grenadas_own_rate(self):
        line = self.calculator.by_code['0201.10.00']
        self.assertEqual((line['national_rate']['rate'], line['national_rate']['cet']), ('30%', '40%'))  # beef: schedule 30%, CET 40%
        self.assertAlmostEqual(self.calculator.calculate('0201.10.00', Inputs(goods_value_usd=1000, origin='United States')).to_dict()['total_tax_usd'], 300.0)

    def test_description_above_and_below_the_code_line_is_joined(self):
        self.assertIn('Of reptiles (including snakes and turtles)', self.calculator.by_code['0208.50.00']['description'])

    def test_schedule_and_list_conflicts_are_reported_not_hidden(self):
        result = self.calculator.calculate('1005.90.00', Inputs(goods_value_usd=1000, origin='Brazil')).to_dict()  # schedule 25%, List A says Free
        self.assertTrue(any('CONFLICT IN THE FILE' in warning for warning in result['warnings']))

    def test_rum_warns_about_the_1961_order(self):
        result = self.calculator.calculate('2208.40.10', Inputs(goods_value_usd=1000, quantity_units=10, origin='Colombia')).to_dict()
        self.assertTrue(any('Import Duty on Rum' in warning for warning in result['warnings']))


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
