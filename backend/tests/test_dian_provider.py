"""Offline tests of the DIAN provider's decisions, the cache and the service (no browser, no network: navigation is faked)."""

import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base
from backend.tax_calc.colombia_dian import navigation
from backend.tax_calc.colombia_dian.cache import TariffCache, is_cacheable
from backend.tax_calc.colombia_dian.dian_types import DianError, TaxLookupRequest, TaxValue
from backend.tax_calc.colombia_dian.parsers import parse_profile
from backend.tax_calc.colombia_dian.provider import DianProvider, _Debug, today_local
from backend.tax_calc.colombia_dian.service import TaxCalculatorService

FIXTURES = Path(__file__).resolve().parent.parent / 'tax_calc' / 'colombia_dian' / 'fixtures'
TODAY = '2026-10-07'


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def value(rate=15.0, concept=None, valid_from='2017-01-01', valid_to=None, raw=None, classification=None):
    return TaxValue(rate=rate, unit='percent', formulaRaw=raw or f'{rate}%', validFrom=valid_from, validTo=valid_to, concept=concept, classification=classification)


class _Table:  # a stand-in for parsers.TaxTable
    def __init__(self, rows, label_header=None):
        self.rows = rows
        self.label_header = label_header
        self.found = True
        self.warnings = []


class _IvaRead:
    def __init__(self, rows, label_header=None):
        self.table = _Table(rows, label_header)


def build(gravamen_rows, iva_rows, iva_header=None, today=TODAY):
    profile = parse_profile(fixture('nomenclature_tomatoes_0702000000.html'))
    return DianProvider()._build_result('0702', '0702000000', profile, today, gravamen_rows, _IvaRead(iva_rows, iva_header), [], [])


class BuildResultTests(unittest.TestCase):
    def test_single_rows_are_calculable(self):
        result = build([value(15, 'GRAVAMEN ARANCELARIO')], [value(19)])
        self.assertTrue(result['calculable'])
        self.assertEqual((result['gravamen']['rate'], result['iva']['rate'], result['ivaStatus']), (15.0, 19.0, 'listed'))
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['product']['chapter'], '07')
        self.assertEqual(result['product']['heading'], '0702')

    def test_two_valid_gravamen_rows_need_input(self):
        rows = [value(15, 'GRAVAMEN ARANCELARIO'), value(34, 'ARANCEL VARIABLE', valid_from='2026-10-01', valid_to='2026-10-15')]
        result = build(rows, [value(19)])
        self.assertIsNone(result['gravamen'])
        self.assertFalse(result['calculable'])
        self.assertEqual(result['needsInput'], [{'tax': 'gravamen', 'reason': 'multiple_valid_rows', 'rowIndexes': [0, 1]}])
        self.assertEqual(len(result['gravamenRows']), 2)  # all rows are returned

    def test_expired_variable_row_is_not_counted_but_warned(self):
        rows = [value(15, 'GRAVAMEN ARANCELARIO'), value(34, 'ARANCEL VARIABLE', valid_from='2026-10-01', valid_to='2026-10-15')]
        result = build(rows, [value(19)], today='2026-10-20')
        self.assertEqual(result['gravamen']['rate'], 15.0)
        self.assertTrue(any('expired on 2026-10-15' in warning for warning in result['warnings']))

    def test_future_row_warns(self):
        result = build([value(15, valid_from='2027-01-01')], [value(19)])
        self.assertIsNone(result['gravamen'])
        self.assertTrue(any('only from 2027-01-01' in warning for warning in result['warnings']))

    def test_conditional_iva_needs_input(self):
        rows = [value(0, 'dispositivos … 22 UVT', raw='0.0 % - EXENTO', classification='exempt'), value(19, 'Excepto: dispositivos … 22 UVT')]
        result = build([value(0, 'GRAVAMEN ARANCELARIO')], rows, iva_header='Nombre del producto')
        self.assertIsNone(result['iva'])
        self.assertEqual(result['needsInput'][0]['reason'], 'conditional')
        self.assertFalse(result['calculable'])

    def test_excluded_iva_is_a_listed_zero_rate_not_a_missing_one(self):
        result = build([value(15)], [value(0, raw='0 % - EXCLUIDO', classification='excluded')])
        self.assertEqual((result['ivaStatus'], result['iva']['rate'], result['iva']['classification']), ('listed', 0.0, 'excluded'))
        self.assertTrue(result['calculable'])

    def test_no_gravamen_is_not_calculable(self):
        result = build([], [value(19)])
        self.assertIsNone(result['gravamen'])
        self.assertFalse(result['calculable'])

    def test_empty_iva_popup_is_not_listed_only_when_the_gravamen_was_found(self):
        result = build([value(15)], [])
        self.assertEqual((result['ivaStatus'], result['iva']), ('not_listed', None))
        self.assertEqual(result['warnings'], [])  # no warning for a normal "no IVA"
        self.assertTrue(result['calculable'])


class _FakeContext:
    pass


class CriticalIvaFailureTests(unittest.TestCase):
    """A failed IVA popup must be an ERROR, never `ivaStatus: not_listed`."""

    def setUp(self):
        self.profile = parse_profile(fixture('nomenclature_tomatoes_0702000000.html'))
        self.provider = DianProvider()
        self.debug = _Debug(None, False)

    def read_iva(self, popup_html=None, popup_error=None, profile=None, gravamen_found=True):
        def fake_open(context, page, button_id, name):
            if popup_error:
                raise popup_error
            return popup_html, 'https://example.test/popup'

        with mock.patch.object(navigation, 'open_measure', fake_open):
            return self.provider._read_measure(_FakeContext(), None, profile or self.profile, 'IVA', self.debug, required=False, gravamen_found=gravamen_found)

    def test_unexpected_popup_is_measure_parse_failed(self):
        with self.assertRaises(DianError) as caught:
            self.read_iva(popup_html=fixture('SYNTHETIC_iva_popup_unexpected.html'))
        self.assertEqual(caught.exception.code, 'MEASURE_PARSE_FAILED')
        self.assertEqual(caught.exception.diagnostics['measureName'], 'IVA')

    def test_popup_that_does_not_open_is_an_error(self):
        with self.assertRaises(DianError) as caught:
            self.read_iva(popup_error=DianError('MEASURE_PARSE_FAILED', 'The IVA popup did not open.'))
        self.assertEqual(caught.exception.code, 'MEASURE_PARSE_FAILED')

    def test_timeout_is_an_error(self):
        with self.assertRaises(DianError) as caught:
            self.read_iva(popup_error=DianError('DIAN_TIMEOUT', 'slow'))
        self.assertEqual(caught.exception.code, 'DIAN_TIMEOUT')

    def test_disabled_icon_with_gravamen_found_is_not_listed(self):
        profile = parse_profile(fixture('SYNTHETIC_nomenclature_iva_icon_disabled.html'))
        read, url, _ = self.read_iva(profile=profile)
        self.assertEqual(read.table.rows, [])
        self.assertIsNone(url)

    def test_disabled_icon_without_a_gravamen_is_an_error(self):
        profile = parse_profile(fixture('SYNTHETIC_nomenclature_iva_icon_disabled.html'))
        with self.assertRaises(DianError):
            self.read_iva(profile=profile, gravamen_found=False)

    def test_empty_popup_rows_parse_as_empty(self):
        read, _, _ = self.read_iva(popup_html=fixture('SYNTHETIC_iva_popup_no_rows.html'))
        self.assertEqual(read.table.rows, [])

    def test_a_good_popup_still_parses(self):
        read, url, _ = self.read_iva(popup_html=fixture('iva_popup_tshirts_6109100000.html'))
        self.assertEqual(read.table.rows[0].rate, 19.0)


class HistoricalDateTests(unittest.TestCase):
    def test_historical_date_is_flagged_not_faked(self):
        provider = DianProvider()
        captured = {}

        def fake_run(req, code, today, warnings):
            captured['warnings'] = list(warnings)
            return {'status': 'ok', 'query': {'resolvedHsCode': code, 'consultationDate': today}, 'warnings': warnings}, 0

        with mock.patch('backend.tax_calc.colombia_dian.provider.run_in_browser_thread', lambda fn, *a, **k: _Done(fn(*a, **k))):
            with mock.patch.object(provider, '_run', fake_run):
                provider.lookup(TaxLookupRequest(country='CO', hsCode='0702000000', date='2020-01-01'))
        self.assertTrue(any('historical lookup' in warning and '2020-01-01' in warning for warning in captured['warnings']))

    def test_invalid_code_is_a_structured_error(self):
        result, _ = DianProvider().lookup(TaxLookupRequest(country='CO', hsCode='12'))
        self.assertEqual(result['error']['code'], 'INVALID_HS_CODE')


class _Done:
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


def memory_cache() -> TariffCache:
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)  # one shared in-memory database for every thread
    Base.metadata.create_all(bind=engine, tables=[models.DianTariffCache.__table__, models.DianCodeAlias.__table__])
    return TariffCache(sessionmaker(bind=engine))


def ok_result(resolved='0702000000', date=None):
    return {
        'status': 'ok',
        'query': {'inputHsCode': resolved, 'resolvedHsCode': resolved, 'consultationDate': date or today_local()},
        'gravamen': {'rate': 15.0},
        'source': {'mainPageUrl': 'https://example.test'},
        'warnings': [],
    }


class CacheTests(unittest.TestCase):
    def test_put_get_and_alias(self):
        cache = memory_cache()
        cache.put('0702', ok_result())
        self.assertEqual(cache.resolve_alias('0702', today_local()), '0702000000')
        self.assertEqual(cache.get('0702000000', today_local())['gravamen']['rate'], 15.0)

    def test_expires_after_the_ttl(self):
        cache = memory_cache()
        cache.put('0702000000', ok_result())
        later = datetime.now(timezone.utc) + timedelta(hours=48)
        self.assertIsNone(cache.get('0702000000', today_local(), now=later))

    def test_only_clean_successes_are_cacheable(self):
        self.assertTrue(is_cacheable(ok_result(), 0))
        self.assertFalse(is_cacheable(ok_result(), 1))  # parse warnings
        self.assertFalse(is_cacheable({'status': 'error', 'error': {}}, 0))
        self.assertFalse(is_cacheable({'status': 'selection_required'}, 0))


class FakeProvider:
    countryCode = 'CO'

    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay
        self.fail = set()

    def lookup(self, req):
        self.calls.append(req.hsCode)
        time.sleep(self.delay)
        if req.hsCode in self.fail:
            return {'status': 'error', 'error': {'code': 'HS_CODE_NOT_FOUND', 'message': 'x'}}, 0
        return ok_result(req.hsCode), 0


def new_service(provider):
    service = TaxCalculatorService(cache=memory_cache())
    service.register(provider)
    return service


class ServiceTests(unittest.TestCase):
    def test_repeat_lookup_hits_the_cache_and_force_refresh_bypasses_it(self):
        provider = FakeProvider()
        service = new_service(provider)
        service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000'))
        second = service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000'))
        self.assertEqual(provider.calls, ['0702000000'])
        self.assertTrue(second['source']['fromCache'])
        # a cache hit reports the code typed THIS time, not the one that filled the cache
        service.cache.put('0702', {**ok_result('0702000000'), 'query': {'inputHsCode': '0702', 'resolvedHsCode': '0702000000', 'consultationDate': today_local()}})
        hit = service.lookup(TaxLookupRequest(country='CO', hsCode='0702'))
        self.assertEqual((hit['query']['inputHsCode'], hit['source']['requestedHsCode']), ('0702', '0702'))
        service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000', forceRefresh=True))
        self.assertEqual(len(provider.calls), 2)

    def test_errors_are_never_cached(self):
        provider = FakeProvider()
        provider.fail.add('0702000000')
        service = new_service(provider)
        service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000'))
        service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000'))
        self.assertEqual(len(provider.calls), 2)

    def test_identical_concurrent_lookups_share_one_run(self):
        provider = FakeProvider(delay=0.4)
        service = new_service(provider)
        results = []
        threads = [threading.Thread(target=lambda: results.append(service.lookup(TaxLookupRequest(country='CO', hsCode='0702000000', forceRefresh=True)))) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(results), 4)

    def test_invalid_code_never_reaches_the_provider(self):
        provider = FakeProvider()
        result = new_service(provider).lookup(TaxLookupRequest(country='CO', hsCode='abc'))
        self.assertEqual(result['error']['code'], 'INVALID_HS_CODE')
        self.assertEqual(provider.calls, [])

    def test_unknown_country_has_no_provider(self):
        with self.assertRaises(KeyError):
            new_service(FakeProvider()).lookup(TaxLookupRequest(country='ZZ', hsCode='0702000000'))

    def test_batch_continues_after_a_failed_code_and_reports_progress(self):
        provider = FakeProvider()
        provider.fail.add('0901111000')
        service = new_service(provider)
        events = []
        results = service.lookup_batch('CO', ['0702000000', '0901111000', '6109100000'], delay_ms=0, on_progress=events.append)
        self.assertEqual([item['result']['status'] for item in results], ['ok', 'error', 'ok'])
        self.assertEqual([event.message for event in events], ['1/3 Processing 0702000000', '2/3 Processing 0901111000', '3/3 Processing 6109100000'])


if __name__ == '__main__':
    unittest.main()
