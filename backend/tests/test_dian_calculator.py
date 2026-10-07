"""Tests of the pure Colombian import-tax calculator (no network)."""

import unittest

from backend.tax_calc.colombia_dian.import_taxes import IVA_NOT_LISTED_NOTE, calculate_import_taxes, iva_base_for_imports
from decimal import Decimal


def percent(rate, **extra):
    return {'rate': rate, 'unit': 'percent', 'formulaRaw': f'{rate}%', 'validFrom': '2017-01-01', 'validTo': None, **extra}


class PercentCaseTests(unittest.TestCase):
    def test_gravamen_then_iva_on_value_plus_gravamen(self):
        result = calculate_import_taxes(1000, percent(15), percent(19))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['gravamen']['amount'], 150.0)
        self.assertEqual(result['iva']['base'], 1150.0)
        self.assertEqual(result['iva']['amount'], 218.5)
        self.assertEqual(result['totalTaxes'], 368.5)
        self.assertEqual(result['totalWithTaxes'], 1368.5)
        self.assertEqual(result['gravamen']['validFrom'], '2017-01-01')  # validity travels with the figures

    def test_excluded_iva_is_zero_with_dians_wording_noted(self):
        iva = percent(0, formulaRaw='0 % - EXCLUIDO', classification='excluded')
        result = calculate_import_taxes(1000, percent(15), iva)
        self.assertEqual((result['status'], result['iva']['amount'], result['totalTaxes']), ('ok', 0.0, 150.0))
        self.assertTrue(any('EXCLUIDO' in note for note in result['notes']))

    def test_iva_base_function_is_the_one_place_to_change(self):
        self.assertEqual(iva_base_for_imports(Decimal('1000'), Decimal('150')), Decimal('1150'))


class NotListedAndMissingTests(unittest.TestCase):
    def test_iva_not_listed_is_zero_with_the_informational_note(self):
        result = calculate_import_taxes(1000, percent(15), None, 'not_listed')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['iva']['amount'], 0.0)
        self.assertIn(IVA_NOT_LISTED_NOTE, result['notes'])
        self.assertEqual(result['totalTaxes'], 150.0)
        self.assertEqual(result['warnings'], [])  # a note, not a warning

    def test_missing_gravamen_is_not_calculable(self):
        result = calculate_import_taxes(1000, None, percent(19))
        self.assertEqual(result['status'], 'not_calculable')
        self.assertIsNone(result['totalTaxes'])


class NonPercentTests(unittest.TestCase):
    def test_non_percent_gravamen_is_not_computed(self):
        gravamen = {'rate': None, 'unit': 'mixed', 'formulaRaw': '15% + USD 5 por kg', 'validFrom': None, 'validTo': None}
        result = calculate_import_taxes(1000, gravamen, percent(19))
        self.assertEqual(result['status'], 'unsupported_formula')
        self.assertEqual(result['gravamen']['formulaRaw'], '15% + USD 5 por kg')
        self.assertIsNone(result['gravamen']['amount'])
        self.assertIsNone(result['totalTaxes'])

    def test_non_percent_iva_is_not_computed_but_gravamen_is_shown(self):
        iva = {'rate': None, 'unit': 'formula', 'formulaRaw': 'según producto', 'validFrom': None, 'validTo': None}
        result = calculate_import_taxes(1000, percent(15), iva)
        self.assertEqual(result['status'], 'unsupported_formula')
        self.assertEqual(result['gravamen']['amount'], 150.0)
        self.assertIsNone(result['iva']['amount'])


class RoundingTests(unittest.TestCase):
    def test_rounds_only_at_the_end_half_up(self):
        # 333.33 x 7.5 % = 24.99975 -> 25.00; intermediate values are exact until the end
        result = calculate_import_taxes('333.33', percent(7.5), percent(0))
        self.assertEqual(result['gravamen']['amount'], 25.0)
        # 0.05 at 10 % = 0.005 -> 0.01 (half up), not banker's rounding to 0.00
        self.assertEqual(calculate_import_taxes('0.05', percent(10), percent(0))['gravamen']['amount'], 0.01)

    def test_no_float_drift(self):
        result = calculate_import_taxes('0.1', percent(10), percent(0), decimals=4)
        self.assertEqual(result['gravamen']['amount'], 0.01)

    def test_negative_value_rejected(self):
        with self.assertRaises(ValueError):
            calculate_import_taxes(-1, percent(15), percent(19))


if __name__ == '__main__':
    unittest.main()
