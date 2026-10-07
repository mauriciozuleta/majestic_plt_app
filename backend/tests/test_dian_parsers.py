"""Offline tests of the DIAN parsers, run against the sanitized fixtures in backend/tax_calc/colombia_dian/fixtures (no network, no browser)."""

import unittest
from pathlib import Path

from backend.tax_calc.colombia_dian.cache import cache_key
from backend.tax_calc.colombia_dian.dian_types import DianError
from backend.tax_calc.colombia_dian.parsers import (
    classify_formula,
    fix_mojibake,
    fold,
    is_not_found,
    is_valid_on,
    normalize_hs_code,
    page_summary,
    parse_date,
    parse_generic_tables,
    parse_listing,
    parse_number,
    parse_profile,
    parse_tax_table,
)

FIXTURES = Path(__file__).resolve().parent.parent / 'tax_calc' / 'colombia_dian' / 'fixtures'


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


class HsCodeTests(unittest.TestCase):
    def test_normalizes_separators_and_keeps_digits_as_typed(self):
        self.assertEqual(normalize_hs_code(' 0702.00.00.00 '), '0702000000')
        self.assertEqual(normalize_hs_code('0702-00'), '070200')
        self.assertEqual(normalize_hs_code('0702'), '0702')  # never padded

    def test_rejects_bad_codes(self):
        for bad in ('', '07', '07020', '12345678901', 'abcd', '0702 AB'):
            with self.assertRaises(DianError) as caught:
                normalize_hs_code(bad)
            self.assertEqual(caught.exception.code, 'INVALID_HS_CODE')


class DateAndNumberTests(unittest.TestCase):
    def test_spanish_dates(self):
        self.assertEqual(parse_date('01-ene-2017'), '2017-01-01')
        self.assertEqual(parse_date('15-OCT-2026'), '2026-10-15')
        self.assertEqual(parse_date('8-ago-2023'), '2023-08-08')
        self.assertEqual(parse_date('31-dic-2019'), '2019-12-31')
        self.assertEqual(parse_date('02-sept-2020'), '2020-09-02')  # accents / long month tolerated

    def test_empty_markers_are_none(self):
        for marker in ('...', '', '-', '  ...  '):
            self.assertIsNone(parse_date(marker))

    def test_bad_date_raises(self):
        with self.assertRaises(ValueError):
            parse_date('mañana')

    def test_colombian_numbers(self):
        self.assertEqual(parse_number('15,5%'), (15.5, []))
        self.assertEqual(parse_number('$1.234,50'), (1234.5, []))
        self.assertEqual(parse_number('5.0 %'), (5.0, []))
        self.assertEqual(parse_number('1.234.567'), (1234567.0, []))
        self.assertEqual(parse_number('19'), (19.0, []))

    def test_ambiguous_separator_is_flagged(self):
        value, warnings = parse_number('1.234')
        self.assertEqual(value, 1234.0)
        self.assertTrue(warnings)

    def test_no_digits(self):
        self.assertEqual(parse_number('n/a'), (None, []))


class FormulaTests(unittest.TestCase):
    def test_percent_variants(self):
        for raw, rate in (('15%', 15.0), ('40 %', 40.0), ('5.0 %', 5.0), ('0.0 %', 0.0), ('15,5 %', 15.5)):
            self.assertEqual(classify_formula(raw)[:2], (rate, 'percent'), raw)

    def test_excluded_and_exempt_are_tags_not_interpretations(self):
        rate, unit, classification, _ = classify_formula('0 % - EXCLUIDO')
        self.assertEqual((rate, unit, classification), (0.0, 'percent', 'excluded'))
        self.assertEqual(classify_formula('0.0 % - EXENTO')[2], 'exempt')

    def test_non_percent_formulas_never_become_a_rate(self):
        self.assertEqual(classify_formula('15% + USD 5 por kg')[:2], (None, 'mixed'))
        self.assertEqual(classify_formula('USD 2.50 por kilo')[:2], (None, 'specific_per_kg'))
        self.assertEqual(classify_formula('$ 1.200 por unidad')[:2], (None, 'specific'))
        self.assertEqual(classify_formula('Según franja de precios')[:2], (None, 'formula'))


class TaxTableTests(unittest.TestCase):
    def test_simple_gravamen(self):
        table = parse_tax_table(fixture('gravamen_popup_tomatoes_0702000000.html'))
        self.assertTrue(table.found)
        self.assertEqual(table.label_header, 'Concepto')
        self.assertEqual(len(table.rows), 1)
        row = table.rows[0]
        self.assertEqual((row.concept, row.rate, row.unit, row.formulaRaw, row.validFrom, row.validTo), ('GRAVAMEN ARANCELARIO', 15.0, 'percent', '15%', '2017-01-01', None))
        self.assertTrue(row.hasLegalBasis)
        self.assertEqual(table.warnings, [])

    def test_multi_row_gravamen_with_variable_tariff(self):
        rows = parse_tax_table(fixture('gravamen_popup_lard_1501100000.html')).rows
        self.assertEqual([r.concept for r in rows], ['GRAVAMEN ARANCELARIO', 'ARANCEL VARIABLE'])
        self.assertEqual((rows[1].rate, rows[1].validFrom, rows[1].validTo), (0.0, '2026-10-01', '2026-10-15'))
        self.assertTrue(is_valid_on(rows[1], '2026-10-07'))
        self.assertFalse(is_valid_on(rows[1], '2026-10-16'))
        self.assertFalse(is_valid_on(rows[1], '2026-09-30'))

    def test_iva_excluded_row(self):
        table = parse_tax_table(fixture('iva_popup_tomatoes_0702000000.html'))
        self.assertIsNone(table.label_header)
        row = table.rows[0]
        self.assertEqual((row.rate, row.unit, row.classification, row.formulaRaw, row.validFrom), (0.0, 'percent', 'excluded', '0 % - EXCLUIDO', '2013-01-01'))

    def test_iva_plain_percent(self):
        row = parse_tax_table(fixture('iva_popup_tshirts_6109100000.html')).rows[0]
        self.assertEqual((row.rate, row.classification), (19.0, None))

    def test_conditional_iva_keeps_the_product_names(self):
        table = parse_tax_table(fixture('iva_popup_phones_8517130000.html'))
        self.assertEqual(table.label_header, 'Nombre del producto')
        self.assertEqual(len(table.rows), 2)
        self.assertEqual((table.rows[0].rate, table.rows[0].classification), (0.0, 'exempt'))
        self.assertEqual(table.rows[1].rate, 19.0)
        self.assertTrue(table.rows[1].concept.startswith('Excepto'))

    def test_popup_without_rows_is_found_but_empty(self):
        table = parse_tax_table(fixture('SYNTHETIC_iva_popup_no_rows.html'))
        self.assertTrue(table.found)
        self.assertEqual(table.rows, [])

    def test_unexpected_popup_is_not_found(self):
        table = parse_tax_table(fixture('SYNTHETIC_iva_popup_unexpected.html'))
        self.assertFalse(table.found)
        summary = page_summary(fixture('SYNTHETIC_iva_popup_unexpected.html'))
        self.assertEqual(summary['title'], 'DIAN - MUISCA')
        self.assertIn('Servicio no disponible', summary['tables'][0]['rawText'])


class PageTests(unittest.TestCase):
    def test_profile(self):
        profile = parse_profile(fixture('nomenclature_tomatoes_0702000000.html'))
        self.assertTrue(profile.recognized)
        self.assertEqual((profile.displayCode, profile.hsCode), ('0702.00.00.00', '0702000000'))
        self.assertIn('Tomates frescos', profile.description)
        self.assertIn('Kilogramo', profile.unit)
        self.assertTrue(profile.measure('Gravamen').importAvailable)
        self.assertTrue(profile.measure('iva').importAvailable)  # found by visible name, any case
        self.assertFalse(profile.measure('Otras tarifas generales').importAvailable)
        self.assertIsNotNone(profile.measure('Gravámenes por acuerdos internacionales'))  # accents tolerated

    def test_disabled_iva_icon(self):
        profile = parse_profile(fixture('SYNTHETIC_nomenclature_iva_icon_disabled.html'))
        self.assertTrue(profile.measure('Gravamen').importAvailable)
        self.assertFalse(profile.measure('IVA').importAvailable)

    def test_listing_of_a_partial_code(self):
        lines = parse_listing(fixture('code_listing_0901.html'))
        self.assertEqual([line.hsCode for line in lines], ['0901111000', '0901119000', '0901120000', '0901211000', '0901212000', '0901220000', '0901900000'])
        self.assertEqual(lines[3].description, '- - - En grano')

    def test_not_found_page(self):
        html = fixture('nomenclature_not_found_9999999999.html')
        self.assertTrue(is_not_found(html))
        self.assertFalse(parse_profile(html).recognized)
        self.assertFalse(is_not_found(fixture('nomenclature_tomatoes_0702000000.html')))


class MiscTests(unittest.TestCase):
    def test_double_encoded_text_from_dian_is_repaired(self):
        self.assertEqual(fix_mojibake('elaboraciÃ³n de cualquier corte'), 'elaboración de cualquier corte')
        self.assertEqual(fix_mojibake('niÃ±o'), 'niño')
        self.assertEqual(fix_mojibake('Cortes finos'), 'Cortes finos')  # clean text untouched

    def test_cache_key(self):
        self.assertEqual(cache_key('0702000000', '2026-10-07'), 'DIAN:0702000000:2026-10-07:v1')

    def test_fold(self):
        self.assertEqual(fold('  Gravámenes   por Acuerdos '), 'gravamenes por acuerdos')

    def test_generic_parser_returns_rows(self):
        tables = parse_generic_tables(fixture('iva_popup_tshirts_6109100000.html'))
        self.assertTrue(any('19%' in table['rawText'] for table in tables))


if __name__ == '__main__':
    unittest.main()
