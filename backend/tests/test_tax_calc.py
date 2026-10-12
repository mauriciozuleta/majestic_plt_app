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


class BarbadosTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Barbados')
        self.calculator.refresh()
        if not self.calculator.info()['ready']:
            self.skipTest('Barbados tariff data not present (use "Update tariff data")')

    def test_the_schedule_sections_were_read(self):
        info = self.calculator.info()
        self.assertGreater(info['lines'], 6500)
        self.assertGreaterEqual(info['section_b_entries'], 80)
        self.assertGreaterEqual(info['section_c_entries'], 80)
        self.assertEqual(self.calculator.by_code['0702.00.00.100']['path'], 'Tomatoes, fresh or chilled. > Cherry tomatoes')  # not under the previous heading (potatoes)

    def test_fresh_tomatoes_199_percent_on_cif_and_vat_zero_rated_as_printed(self):
        result = self.calculator.calculate('0702.00.00.100', Inputs(goods_value_usd=1000, freight_usd=100, quantity_kg=1000, origin='Colombia')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Customs duty'], 1100 * 1.99)
        vat = next(tax for tax in result['taxes'] if tax['name'].startswith('Value added'))
        self.assertEqual((vat['amount'], vat['recoverable']), (0.0, True))  # the tariff line prints 0.0%

    def test_vat_rate_is_the_one_printed_on_the_line(self):
        result = self.calculator.calculate('0201.10.00.000', Inputs(goods_value_usd=1000, origin='United States')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Customs duty'], 300.0)  # beef 30%
        self.assertAlmostEqual(_by_name(result)['Value added tax (VAT)'], 1300 * 0.175)

    def test_caricom_origin_is_duty_free(self):
        self.assertEqual(self.calculator.calculate('0702.00.00.100', Inputs(goods_value_usd=1000, quantity_kg=1000, origin='Jamaica')).to_dict()['total_tax_usd'], 0.0)

    def test_section_b_goods_pay_60_percent_whatever_section_a_says(self):
        line = next(line for line in self.calculator.lines if line['code'].startswith('6112.49'))
        result = self.calculator.calculate(line['code'], Inputs(goods_value_usd=1000, origin='China')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Customs duty'], 600.0)
        self.assertTrue(any('Section B' in note for note in result['notes']))

    def test_special_safeguard_formula(self):
        from backend.tax_calc.barbados import safeguard_additional_duty

        self.assertEqual(safeguard_additional_duty(2.86, 2.86 * 0.95), 0.0)  # within 10% of the trigger
        self.assertAlmostEqual(safeguard_additional_duty(2.86, 2.0), 2.86 * 0.3 * ((2.86 - 2.0) / 2.86 - 0.10), places=6)  # a 30.07% drop
        self.assertAlmostEqual(safeguard_additional_duty(2.86, 2.86 * 0.5), 2.86 * (0.3 * 0.30 + 0.5 * 0.10), places=6)
        self.assertAlmostEqual(safeguard_additional_duty(2.86, 2.86 * 0.2), 2.86 * (0.09 + 0.10 + 0.105 + 0.045), places=6)

    def test_chicken_wings_pay_the_safeguard_only_when_the_price_is_below_the_trigger(self):
        cheap = self.calculator.calculate('0207.14.20.000', Inputs(goods_value_usd=1000, quantity_kg=1000, origin='United States')).to_dict()
        extra = _by_name(cheap)['Special safeguard additional duty']
        self.assertAlmostEqual(extra, 2.86 * 0.3 * ((2.86 - 2.0) / 2.86 - 0.10) * 1000 / 2.0, places=2)  # BBD 2.00/kg against a BBD 2.86 trigger
        dear = self.calculator.calculate('0207.14.20.000', Inputs(goods_value_usd=2000, quantity_kg=1000, origin='United States')).to_dict()
        self.assertNotIn('Special safeguard additional duty', _by_name(dear))
        self.assertFalse(self.calculator.calculate('0207.14.20.000', Inputs(goods_value_usd=1000, origin='United States')).complete)  # no quantity: not computable

    def test_countervailing_duty_applies_only_to_goods_from_trinidad_and_tobago(self):
        from_tt = self.calculator.calculate('0403.10.00.000', Inputs(goods_value_usd=1000, quantity_units=1000, origin='Trinidad and Tobago')).to_dict()
        self.assertAlmostEqual(next(t['amount'] for t in from_tt['taxes'] if t['name'].startswith('Countervailing')), 1000 * 0.33 / 2.0)  # BBD 0.33 per litre
        self.assertEqual(_by_name(from_tt)['Customs duty'], 0.0)  # CARICOM origin: the CET is waived, the countervailing duty is not
        other = self.calculator.calculate('0403.10.00.000', Inputs(goods_value_usd=1000, quantity_units=1000, origin='Canada')).to_dict()
        self.assertFalse(any(t['name'].startswith('Countervailing') for t in other['taxes']))

    def test_excise_percentage_is_charged_on_cif_plus_duty(self):
        result = self.calculator.calculate('2009.11.10.200', Inputs(goods_value_usd=1000, quantity_kg=1000, origin='Canada')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Excise tax'], (1000 + 400) * 0.10)  # duty 40%, excise 10%

    def test_inspection_fee_per_head_needs_the_number_of_head(self):
        with_units = self.calculator.calculate('0102.90.00.000', Inputs(goods_value_usd=5000, quantity_units=10, origin='Canada')).to_dict()
        self.assertAlmostEqual(_by_name(with_units)['Inspection fee'], 10 * 10.0 / 2.0)  # BBD 10 each
        self.assertFalse(self.calculator.calculate('0102.90.00.000', Inputs(goods_value_usd=5000, origin='Canada')).complete)

    def test_a_specific_duty_is_reported_not_guessed(self):
        line = next((line for line in self.calculator.lines if line['duty'] is None), None)
        if line is None:
            self.skipTest('every duty was readable')
        self.assertFalse(self.calculator.calculate(line['code'], Inputs(goods_value_usd=100)).complete)

    def test_schedule_and_list_conflicts_are_reported(self):
        result = self.calculator.calculate('0207.14.20.000', Inputs(goods_value_usd=2000, quantity_kg=1000, origin='United States')).to_dict()
        self.assertTrue(any('CONFLICT IN THE FILE' in warning for warning in result['warnings']))  # schedule 184%, List A gives Barbados Free

    def test_eu_origin_gets_the_epa_warning(self):
        result = self.calculator.calculate('0201.10.00.000', Inputs(goods_value_usd=1000, origin='Germany')).to_dict()
        self.assertTrue(any('EPA' in warning for warning in result['warnings']))


class HigherRateRuleTests(unittest.TestCase):
    """STANDING RULE: when two parts of a document disagree on a line's rate, the HIGHER rate is used and the conflict is still reported."""

    def test_the_helper(self):
        from backend.tax_calc.base import higher_rate, rate_pct

        self.assertEqual((rate_pct('Free'), rate_pct('40%'), rate_pct('$2.64'), rate_pct(None)), (0.0, 40.0, None, None))
        self.assertEqual(higher_rate('184%', 'Free'), '184%')
        self.assertEqual(higher_rate('5%', '10%'), '10%')
        self.assertEqual(higher_rate('Free', '15%'), '15%')
        self.assertEqual(higher_rate('20%', '20%'), '20%')
        self.assertEqual(higher_rate('$2.64', '15%'), '15%')  # a side that is not a percentage is ignored
        self.assertEqual(higher_rate('15%', None), '15%')

    def test_barbados_uses_the_higher_of_schedule_and_list(self):
        calculator = tax_calc.get('Barbados')
        calculator.refresh()
        if not calculator.info()['ready']:
            self.skipTest('Barbados data not present')
        from backend.tax_calc.base import rate_pct

        lower_in_schedule = next((line for line in calculator.lines if line['duty'] and calculator._list_value(line) and (rate_pct(calculator._list_value(line)['rate']) or 0) > (rate_pct(line['duty']) or 0)), None)
        if lower_in_schedule is not None:  # the list is higher: its rate is used
            listed = calculator._list_value(lower_in_schedule)['rate']
            result = calculator.calculate(lower_in_schedule['code'], Inputs(goods_value_usd=1000, origin='Canada')).to_dict()
            self.assertAlmostEqual(_by_name(result)['Customs duty'], 1000 * rate_pct(listed) / 100)
            self.assertTrue(any('CONFLICT IN THE FILE' in warning and 'HIGHER' in warning for warning in result['warnings']))
        pork = calculator.calculate('0203.11.00.000', Inputs(goods_value_usd=1000, quantity_kg=1000, origin='Canada')).to_dict()  # schedule 184%, List Free
        self.assertAlmostEqual(_by_name(pork)['Customs duty'], 1840.0)
        self.assertTrue(any('CONFLICT IN THE FILE' in warning for warning in pork['warnings']))

    def test_grenada_uses_the_higher_of_schedule_and_list(self):
        calculator = tax_calc.get('Grenada')
        calculator.refresh()
        if not calculator.info()['ready']:
            self.skipTest('Grenada data not present')
        maize = calculator.calculate('1005.90.00', Inputs(goods_value_usd=1000, origin='Brazil')).to_dict()  # schedule 25%, List A Free -> 25%
        self.assertAlmostEqual(_by_name(maize)['Customs duty'], 250.0)
        jewellery = calculator.calculate('7113.20.00', Inputs(goods_value_usd=1000, origin='Brazil')).to_dict()  # schedule 30%, List C 35% -> 35%
        self.assertAlmostEqual(_by_name(jewellery)['Customs duty'], 350.0)
        for result in (maize, jewellery):
            self.assertTrue(any('CONFLICT IN THE FILE' in warning and 'HIGHER' in warning for warning in result['warnings']))

    def test_grenada_rum_order_is_used_when_it_is_higher_than_the_cet_rate(self):
        calculator = tax_calc.get('Grenada')
        calculator.refresh()
        if not calculator.info()['ready']:
            self.skipTest('Grenada data not present')
        small = calculator.calculate('2208.40.10', Inputs(goods_value_usd=1000, quantity_units=100, origin='Colombia')).to_dict()  # Order 936 EC$ = 346.67 USD < 35% of 1,000
        self.assertAlmostEqual(small['total_tax_usd'], 350.0)
        large = calculator.calculate('2208.40.10', Inputs(goods_value_usd=1000, quantity_units=200, origin='Colombia')).to_dict()  # Order 1,872 EC$ = 693.33 USD > 350
        self.assertAlmostEqual(large['total_tax_usd'], 200 * 9.36 / 2.7, places=2)
        self.assertTrue(any('HIGHER duty is used' in warning for warning in large['warnings']))

    def test_saint_lucia_uses_the_higher_of_schedule_and_list(self):
        calculator = tax_calc.get('Saint Lucia')
        calculator.refresh()
        if not calculator.info()['ready']:
            self.skipTest('Saint Lucia data not present')
        line = calculator.by_code['0702.00.00']
        saved = line['national_rate']
        try:
            line['national_rate'] = {'rate': '60%', 'list': 'A', 'cet': '40%'}  # a list rate above the schedule's 40%
            result = calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, origin='Colombia')).to_dict()
            self.assertAlmostEqual(_by_name(result)['Customs duty'], 600.0)
            self.assertTrue(any('CONFLICT IN THE FILE' in warning for warning in result['warnings']))
            line['national_rate'] = {'rate': 'Free', 'list': 'A', 'cet': '40%'}  # a list rate below the schedule's: the schedule's 40% stays
            result = calculator.calculate('0702.00.00', Inputs(goods_value_usd=1000, origin='Colombia')).to_dict()
            self.assertAlmostEqual(_by_name(result)['Customs duty'], 400.0)
        finally:
            line['national_rate'] = saved


class TurksCaicosTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Turks and Caicos Islands')
        self.calculator.refresh()
        if not self.calculator.info()['ready']:
            self.skipTest('Turks and Caicos tariff data not present (use "Update tariff data")')

    def test_the_whole_table_was_read(self):
        info = self.calculator.info()
        self.assertGreaterEqual(info['lines'], 5300)
        self.assertGreaterEqual(info['specific_rate_lines'], 30)
        self.assertGreaterEqual(info['landed_cost_lines'], 40)
        self.assertEqual(self.calculator.by_code['0702.000']['description'], 'Tomatoes, fresh or chilled.')  # heading and code share one line in the file

    def test_duty_free_food_still_pays_the_7_5_percent_processing_fee(self):
        result = self.calculator.calculate('0207.142', Inputs(goods_value_usd=1000, quantity_kg=1000, origin='United States')).to_dict()
        self.assertEqual(_by_name(result)['Customs duty'], 0.0)
        self.assertAlmostEqual(_by_name(result)['Customs processing fee'], 75.0)

    def test_freight_and_insurance_charge_and_the_duty_base(self):
        result = self.calculator.calculate('0207.142', Inputs(goods_value_usd=1000, freight_usd=200, insurance_usd=20, origin='United States')).to_dict()
        self.assertAlmostEqual(_by_name(result)['Charge on insurance and freight'], 220 * 0.075)
        self.assertAlmostEqual(_by_name(result)['Customs processing fee'], 75.0)  # on the goods, not on freight
        paint = next(line for line in self.calculator.lines if line['rate'] == '30%' and not line['landed_cost'])
        duty = self.calculator.calculate(paint['code'], Inputs(goods_value_usd=1000, freight_usd=200, insurance_usd=20)).to_dict()
        self.assertAlmostEqual(_by_name(duty)['Customs duty'], 300.0)  # duty on the value of the goods, freight and insurance excluded

    def test_building_materials_pay_5_percent_on_freight_and_insurance(self):
        result = self.calculator.calculate('2505.100', Inputs(goods_value_usd=1000, freight_usd=100)).to_dict()
        self.assertAlmostEqual(_by_name(result)['Charge on insurance and freight'], 5.0)

    def test_specific_duties_per_gallon_and_per_thousand(self):
        beer = self.calculator.calculate('2203.010', Inputs(goods_value_usd=1000, quantity_units=100)).to_dict()
        self.assertAlmostEqual(_by_name(beer)['Customs duty (specific)'], 1191.0)  # $11.91 per imperial gallon
        cigarettes = self.calculator.calculate('2402.200', Inputs(goods_value_usd=1000, quantity_units=100000)).to_dict()
        self.assertAlmostEqual(_by_name(cigarettes)['Customs duty (specific)'], 9052.0)  # $90.52 per 1,000
        self.assertFalse(self.calculator.calculate('2203.010', Inputs(goods_value_usd=1000)).complete)  # no quantity: not computable

    def test_fuel_pays_the_tariff_duty_plus_85_cents_a_gallon(self):
        result = self.calculator.calculate('2710.196', Inputs(goods_value_usd=1000, quantity_units=500)).to_dict()  # motor spirit $0.44/gal
        self.assertAlmostEqual(_by_name(result)['Customs duty (specific)'], 220.0)
        self.assertAlmostEqual(_by_name(result)['Additional import duty on fuel'], 425.0)

    def test_vehicles_pay_on_the_landed_cost(self):
        result = self.calculator.calculate('8702.101', Inputs(goods_value_usd=20000, freight_usd=1500, insurance_usd=100)).to_dict()
        self.assertAlmostEqual(_by_name(result)['Customs duty'], 21600 * 0.35)
        self.assertNotIn('Charge on insurance and freight', _by_name(result))  # not charged on motor vehicles

    def test_a_line_without_a_printed_rate_is_incomplete(self):
        result = self.calculator.calculate('0204.430', Inputs(goods_value_usd=1000)).to_dict()
        self.assertFalse(result['complete'])

    def test_no_caricom_waiver(self):
        self.assertEqual(self.calculator.calculate('2203.010', Inputs(goods_value_usd=1000, quantity_units=100, origin='Jamaica')).to_dict()['total_tax_usd'], 1191.0 + 75.0)


class SintMaartenTests(unittest.TestCase):
    def setUp(self):
        self.calculator = tax_calc.get('Sint Maarten (Dutch part)')

    def test_registered_and_ready_without_any_data_file(self):
        self.assertIsNotNone(self.calculator)
        self.assertTrue(self.calculator.info()['ready'])

    def test_every_good_pays_zero_duty(self):
        result = self.calculator.calculate('0000.00', Inputs(goods_value_usd=5000, quantity_kg=100, freight_usd=300, origin='Colombia')).to_dict()
        self.assertEqual(result['total_tax_usd'], 0)
        self.assertTrue(result['complete'])
        self.assertEqual(result['landed_cost_usd'], 5300)
        self.assertTrue(any('gasoline' in warning for warning in result['warnings']))

    def test_any_hs_code_maps_to_the_uniform_line_with_a_zero_multiplier(self):
        self.assertEqual(len(mapping.lines_for_hs(self.calculator, '070200')), 1)
        computed = mapping.multiplier_for(self.calculator, {'name': 'Tomato', 'hs_code': '070200', 'price_usd_kg': 2.0}, 'China')
        self.assertEqual(computed['status'], 'ok')
        self.assertEqual(computed['tax_multiplier'], 0)
        self.assertEqual(computed['landed_multiplier'], 1)


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
