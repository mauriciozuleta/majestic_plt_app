"""Tests of the Global Tourism & Economic Dependency module. No test reaches the network: the World Bank answers are faked."""

import base64
import io
import unittest
from decimal import Decimal
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base, get_db
from backend.routers import tourism as tourism_router
from backend.tourism import calc, constants as c, exporter, http, quality, registry, service, unsd, worldbank, wttc

# (iso2, iso3, name, WB region id)
COUNTRIES = [
    ('JM', 'JAM', 'Jamaica', 'LCN'), ('BB', 'BRB', 'Barbados', 'LCN'), ('BS', 'BHS', 'Bahamas, The', 'LCN'), ('US', 'USA', 'United States', 'NAC'),
    ('CO', 'COL', 'Colombia', 'LCN'), ('ES', 'ESP', 'Spain', 'ECS'), ('JP', 'JPN', 'Japan', 'EAS'), ('AW', 'ABW', 'Aruba', 'LCN'), ('TR', 'TUR', 'Turkiye', 'ECS'),
]
# receipts / gdp / population by country -> {year: value}; JM has receipts for 2019 only and GDP for 2019 and 2020
DATA = {
    'ST.INT.RCPT.CD': {'JAM': {2019: 3_000_000_000.0}, 'BRB': {2019: 1_000_000_000.0, 2020: 400_000_000.0}, 'BHS': {2019: 3_500_000_000.0}, 'USA': {2019: 200e9}, 'COL': {2019: 6e9}, 'ESP': {2019: 80e9}, 'JPN': {2019: 46e9}},
    'NY.GDP.MKTP.CD': {'JAM': {2019: 15_000_000_000.0, 2020: 13_000_000_000.0}, 'BRB': {2019: 5_000_000_000.0, 2020: 4_400_000_000.0}, 'BHS': {2019: 13e9}, 'USA': {2019: 21e12}, 'COL': {2019: 323e9}, 'ESP': {2019: 1.4e12}, 'JPN': {2019: 5.1e12}},
    'SP.POP.TOTL': {'JAM': {2019: 2_900_000.0, 2020: 2_950_000.0}, 'BRB': {2019: 287_000.0}, 'BHS': {2019: 390_000.0}, 'USA': {2019: 328e6}, 'COL': {2019: 50e6}, 'ESP': {2019: 47e6}, 'JPN': {2019: 126e6}},
}


def fake_world_bank_countries():
    return [{'id': iso3, 'iso2Code': iso2, 'name': name, 'region': {'id': region}, 'adminregion': {'value': ''}} for iso2, iso3, name, region in COUNTRIES]


# UN SDG API fixtures: area list (M49) and the ST_GDP_ZS series. Barbados and Grenada report nothing; "World" and "Europe" are aggregates.
UN_AREAS = [
    {'geoAreaCode': '388', 'geoAreaName': 'Jamaica'}, {'geoAreaCode': '52', 'geoAreaName': 'Barbados'}, {'geoAreaCode': '44', 'geoAreaName': 'Bahamas'},
    {'geoAreaCode': '840', 'geoAreaName': 'United States of America'}, {'geoAreaCode': '170', 'geoAreaName': 'Colombia'}, {'geoAreaCode': '724', 'geoAreaName': 'Spain'},
    {'geoAreaCode': '392', 'geoAreaName': 'Japan'}, {'geoAreaCode': '308', 'geoAreaName': 'Grenada'}, {'geoAreaCode': '792', 'geoAreaName': 'Türkiye'},
    {'geoAreaCode': '1', 'geoAreaName': 'World'}, {'geoAreaCode': '150', 'geoAreaName': 'Europe'},
]


def un_record(code, name, year, value, *, units='PERCENT', agency='National Statistics Office', nature='CA', footnotes=('TDGVA used as proxy',), reporting='G'):
    return {'geoAreaCode': code, 'geoAreaName': name, 'timePeriodStart': float(year), 'value': value, 'valueType': 'Float', 'source': agency, 'footnotes': list(footnotes),
            'attributes': {'Nature': nature, 'Units': units}, 'dimensions': {'Reporting Type': reporting}}


UN_RECORDS = [
    un_record('388', 'Jamaica', 2019, '9.8'), un_record('388', 'Jamaica', 2018, '9.2'), un_record('44', 'Bahamas', 2012, '15.16544', footnotes=('Estimate',)),
    un_record('840', 'United States of America', 2023, '3.03', footnotes=()), un_record('170', 'Colombia', 2019, '2.5'), un_record('724', 'Spain', 2019, '5.0'),
    un_record('392', 'Japan', 2019, '1.9'), un_record('1', 'World', 2019, '4.4'), un_record('150', 'Europe', 2019, '4.0'), un_record('792', 'Türkiye', 2019, None),
]


def fake_unsd(url, params):
    if url.endswith('/GeoArea/List'):
        return UN_AREAS
    if url.endswith('/Series/Data'):
        size, page = int(params.get('pageSize', 25)), int(params.get('page', 1))
        total = len(UN_RECORDS)
        return {'size': size, 'totalElements': total, 'totalPages': -(-total // size), 'pageNumber': page, 'data': UN_RECORDS[(page - 1) * size: page * size]}
    if '/GeoArea/' in url and url.endswith('/DataSlice'):
        code = url.split('/GeoArea/')[1].split('/')[0]
        items = [{'value': r['value'], 'timePeriodStart': str(int(r['timePeriodStart'])), 'Reporting Type': 'G'} for r in UN_RECORDS if r['geoAreaCode'] == code and r['value']]
        return {'series': 'ST_GDP_ZS', 'geoAreaCode': int(code), 'geoAreaName': 'x', 'dimensions': items}
    raise AssertionError(f'unexpected UN URL {url}')


def fake_get_json(url, params=None, **kwargs):
    if 'unstats.un.org' in url:
        return fake_unsd(url, params or {})
    indicator = url.rsplit('/', 1)[-1]
    isos = url.split('/country/')[1].split('/')[0].split(';')
    items = []
    for iso3 in isos:
        for year in range(2018, 2023):
            value = DATA[indicator].get(iso3, {}).get(year)
            items.append({'indicator': {'id': indicator}, 'country': {'id': iso3[:2]}, 'countryiso3code': iso3, 'date': str(year), 'value': value, 'obs_status': ''})
    return [{'page': 1, 'pages': 1, 'per_page': 1000, 'total': len(items), 'lastupdated': '2026-01-01'}, items]


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine, tables=[models.TourismCountry.__table__, models.TourismObservation.__table__, models.TourismProvider.__table__,
                                                      models.TourismImportJob.__table__, models.CountryReferenceCatalog.__table__])
        self.db = sessionmaker(bind=self.engine)()
        patches = [mock.patch.object(registry, 'fetch_world_bank_countries', fake_world_bank_countries), mock.patch.object(http, 'get_json', fake_get_json)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        registry.seed_registry(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()


class WorldBankTests(unittest.TestCase):
    def test_normalizes_rows_drops_nulls_and_follows_pagination(self):
        pages = {
            1: [{'page': 1, 'pages': 2, 'lastupdated': '2026-02-01'}, [{'countryiso3code': 'JAM', 'country': {'id': 'JM'}, 'date': '2019', 'value': 3.5e9, 'obs_status': ''},
                                                                      {'countryiso3code': 'JAM', 'country': {'id': 'JM'}, 'date': '2020', 'value': None}]],
            2: [{'page': 2, 'pages': 2, 'lastupdated': '2026-02-01'}, [{'countryiso3code': 'BRB', 'country': {'id': 'BB'}, 'date': '2019', 'value': 1.0e9}]],
        }
        calls = []

        def fake(url, params=None, **kwargs):
            calls.append((url, params['page']))
            return pages[params['page']]

        with mock.patch.object(http, 'get_json', fake):
            rows, edition = worldbank.fetch_indicator(['JAM', 'BRB'], 'ST.INT.RCPT.CD')
        self.assertEqual([(r['iso3'], r['year']) for r in rows], [('JAM', 2019), ('BRB', 2019)])
        self.assertEqual(edition, '2026-02-01')
        self.assertEqual([page for _, page in calls], [1, 2])
        self.assertIn('JAM;BRB', calls[0][0])

    def test_api_error_message_becomes_a_provider_error(self):
        with mock.patch.object(http, 'get_json', lambda *a, **k: [{'message': [{'id': '120', 'key': 'Invalid value', 'value': 'The provided parameter value is not valid'}]}]):
            with self.assertRaises(http.ProviderError):
                worldbank.fetch_indicator(['XXX'], 'ST.INT.RCPT.CD')

    def test_retry_with_exponential_backoff_then_success(self):
        class Response:
            def __init__(self, status, payload=None):
                self.status_code, self._payload = status, payload

            def json(self):
                return self._payload

        answers = [Response(503), Response(429), Response(200, {'ok': True})]
        sleeps = []
        with mock.patch.object(http, 'fetch', lambda *a, **k: answers.pop(0)), mock.patch.object(http.time, 'sleep', sleeps.append):
            self.assertEqual(http.get_json('https://example.test/x', ttl_hours=0, backoff=0.5), {'ok': True})
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_gives_up_after_the_retries(self):
        class Response:
            status_code = 500

        with mock.patch.object(http, 'fetch', lambda *a, **k: Response()), mock.patch.object(http.time, 'sleep', lambda s: None):
            with self.assertRaises(http.ProviderError):
                http.get_json('https://example.test/y', ttl_hours=0)


class CalculationTests(unittest.TestCase):
    def test_dependency_is_decimal_exact(self):
        self.assertEqual(calc.tourism_dependency(3_000_000_000, 15_000_000_000), Decimal('20.0000'))
        self.assertEqual(calc.tourism_dependency('1', '3'), Decimal('33.3333'))

    def test_no_ratio_without_both_values_or_with_a_zero_gdp(self):
        self.assertIsNone(calc.tourism_dependency(None, 100))
        self.assertIsNone(calc.tourism_dependency(100, None))
        self.assertIsNone(calc.tourism_dependency(100, 0))
        self.assertIsNone(calc.tourism_dependency(-5, 100))

    def test_quality_labels(self):
        self.assertEqual(quality.validate(c.POPULATION, 100.0, 'persons', 2024, today_year=2026)[0], c.VERIFIED)
        self.assertEqual(quality.validate(c.POPULATION, 100.0, 'persons', 2015, today_year=2026)[0], c.HISTORICAL)
        self.assertEqual(quality.validate(c.POPULATION, -1.0, 'persons', 2024, today_year=2026)[0], c.REQUIRES_REVIEW)
        self.assertEqual(quality.validate(c.TOURISM_GDP_TOTAL, 0.12, '%', 2024, today_year=2026)[0], c.VERIFIED)  # 0.12% is a valid share; fractions are caught at import
        self.assertEqual(quality.validate(c.TOURISM_GDP_TOTAL, 120.0, '%', 2024, today_year=2026)[0], c.REQUIRES_REVIEW)
        self.assertEqual(quality.validate(c.TOURISM_RECEIPTS, 5.0, 'persons', 2024, today_year=2026)[0], c.REQUIRES_REVIEW)  # wrong unit
        self.assertEqual(quality.validate(c.TOURISM_DEPENDENCY, 5.0, '%', 2024, is_calculated=True, today_year=2026)[0], c.CALCULATED_STATUS)
        self.assertEqual(quality.validate(c.POPULATION, None, 'persons', 2024)[0], c.MISSING)


class RegistryTests(DatabaseCase):
    def test_codes_come_from_the_world_bank_list_and_territories_are_marked(self):
        jamaica = self.db.get(models.TourismCountry, 'JM')
        self.assertEqual((jamaica.iso_alpha3, jamaica.region, jamaica.territory_status), ('JAM', 'Caribbean', 'country'))
        aruba = self.db.get(models.TourismCountry, 'AW')
        self.assertEqual((aruba.territory_status, aruba.parent_country, aruba.region), ('territory', 'NL', 'Caribbean'))
        self.assertEqual(self.db.get(models.TourismCountry, 'ES').region, 'Europe')
        self.assertEqual(self.db.get(models.TourismCountry, 'JP').region, 'Asia')

    def test_resolves_alpha2_and_alpha3_and_reports_unknown_codes(self):
        found, unknown = registry.resolve_codes(self.db, ['jam', 'BB', 'ZZZ', 'JM'])
        self.assertEqual([row.country_id for row in found], ['JM', 'BB'])
        self.assertEqual(unknown, ['ZZZ'])

    def test_provider_names_are_reconciled(self):
        matcher = registry.NameMatcher(self.db)
        self.assertEqual(matcher.match('Bahamas').country_id, 'BS')
        self.assertEqual(matcher.match('The Bahamas').country_id, 'BS')
        self.assertEqual(matcher.match('USA').country_id, 'US')
        self.assertEqual(matcher.match('Türkiye').country_id, 'TR')
        self.assertIsNone(matcher.match('Atlantis'))

    def test_a_manual_territory_gets_no_invented_world_bank_coverage(self):
        row = registry.add_manual_country(self.db, name='Anguilla', iso2='ai', iso3=None, region='Caribbean', territory=True, parent='gb')
        self.assertEqual((row.country_id, row.iso_alpha3, row.in_world_bank, row.territory_status), ('AI', None, False, 'territory'))
        service.compare(self.db, ['AI'], None)  # must not call the World Bank for it
        self.assertEqual(self.db.query(models.TourismObservation).filter_by(country_id='AI').count(), 0)
        with self.assertRaises(ValueError):
            registry.add_manual_country(self.db, name='Bad', iso2='X', iso3=None, region='Caribbean')


class ComparisonTests(DatabaseCase):
    def test_multi_country_comparison_caribbean_and_global(self):
        data = service.compare(self.db, ['JM', 'BB', 'BS', 'US', 'CO', 'ES', 'JP'], 2019)
        rows = {row['iso_alpha2']: row['indicators'] for row in data['rows']}
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows['JM'][c.TOURISM_DEPENDENCY]['value'], 20.0)
        self.assertEqual(rows['JP'][c.TOURISM_RECEIPTS]['value'], 46e9)
        self.assertEqual(rows['US'][c.POPULATION]['value'], 328e6)
        self.assertAlmostEqual(rows['BS'][c.TOURISM_DEPENDENCY]['value'], 26.9231, places=4)

    def test_wttc_indicators_are_not_estimated_when_no_file_is_loaded(self):
        row = service.compare(self.db, ['JM'], 2019)['rows'][0]['indicators']
        self.assertIsNone(row[c.TOURISM_GDP_TOTAL]['value'])
        self.assertIn('WTTC', row[c.TOURISM_GDP_TOTAL]['reason'])
        self.assertIsNone(row[c.TOURISM_EMPLOYMENT]['value'])

    def test_a_missing_year_is_reported_not_borrowed_from_another_year(self):
        row = service.compare(self.db, ['JM'], 2020)['rows'][0]['indicators']
        self.assertIsNone(row[c.TOURISM_RECEIPTS]['value'])  # Jamaica has receipts for 2019 only
        self.assertIn('2019', row[c.TOURISM_RECEIPTS]['reason'])
        self.assertIsNone(row[c.TOURISM_DEPENDENCY]['value'])  # GDP 2020 exists but receipts 2020 do not: no ratio
        self.assertEqual(row[c.GDP_USD]['value'], 13e9)

    def test_receipts_and_gdp_of_different_years_never_make_a_ratio(self):
        service.compare(self.db, ['JM'], None)
        years = [o.reference_year for o in self.db.query(models.TourismObservation).filter_by(country_id='JM', indicator_code=c.TOURISM_DEPENDENCY)]
        self.assertEqual(years, [2019])

    def test_latest_shows_each_indicators_own_year(self):
        row = service.compare(self.db, ['BB'], None)['rows'][0]['indicators']
        self.assertEqual((row[c.TOURISM_RECEIPTS]['year'], row[c.TOURISM_DEPENDENCY]['year'], row[c.POPULATION]['year']), (2020, 2020, 2019))

    def test_a_repeat_sync_updates_the_same_row_and_other_sources_are_kept(self):
        service.compare(self.db, ['JM'], 2019)
        count = self.db.query(models.TourismObservation).count()
        service.compare(self.db, ['JM'], 2019, refresh=True)
        self.assertEqual(self.db.query(models.TourismObservation).count(), count)
        jamaica = self.db.get(models.TourismCountry, 'JM')
        service.upsert_observation(self.db, country=jamaica, indicator_code=c.TOURISM_RECEIPTS, year=2019, value_text='2900000000', source=c.IDB, dataset='test', url=None)
        self.db.commit()
        sources = {o.data_source for o in self.db.query(models.TourismObservation).filter_by(country_id='JM', indicator_code=c.TOURISM_RECEIPTS, reference_year=2019)}
        self.assertEqual(sources, {c.WORLD_BANK, c.IDB})
        self.assertEqual(service.pick(self.db, jamaica, c.TOURISM_RECEIPTS, 2019)['source'], c.WORLD_BANK)  # priority, not recency

    def test_provider_failure_returns_stored_data_with_a_warning(self):
        service.compare(self.db, ['JM'], 2019)

        def boom(*args, **kwargs):
            raise http.ProviderError('down')

        with mock.patch.object(http, 'get_json', boom):
            data = service.compare(self.db, ['JM'], 2019, refresh=True)
        self.assertTrue(any('World Bank unavailable' in warning for warning in data['warnings']))
        self.assertEqual(data['rows'][0]['indicators'][c.POPULATION]['value'], 2_900_000.0)
        self.assertEqual(self.db.get(models.TourismProvider, c.WORLD_BANK).connection_status, 'error')

    def test_disabled_provider_is_not_called(self):
        service.ensure_providers(self.db)
        self.db.get(models.TourismProvider, c.WORLD_BANK).enabled = False
        self.db.get(models.TourismProvider, c.UNSD).enabled = False
        self.db.commit()
        with mock.patch.object(http, 'get_json', side_effect=AssertionError('must not be called')):
            data = service.compare(self.db, ['JM'], 2019)
        self.assertTrue(data['warnings'])

    def test_history_series(self):
        series = service.history(self.db, 'BB', 2019, 2020)['series']
        self.assertEqual([p['year'] for p in series[c.TOURISM_DEPENDENCY]], [2019, 2020])
        self.assertEqual([p['value'] for p in series[c.TOURISM_DEPENDENCY]], [20.0, 9.0909])


class WttcImportTests(DatabaseCase):
    CSV_WIDE = (
        'Country,Year,Total contribution of travel & tourism to GDP (% of GDP),Total contribution of travel & tourism to employment (% of total employment)\n'
        'Jamaica,2019,34.5,35.1\nBahamas,2019,46.0,50.2\nAtlantis,2019,10,10\nBarbados,2019,35.5,abc\nBarbados,2019,36.0,\n'
    )

    def test_csv_import_normalizes_countries_and_reports_rejections(self):
        job = service.import_wttc(self.db, file_name='wttc.csv', content=self.CSV_WIDE.encode(), edition='2025 release')
        self.assertEqual(job['provider'], 'WTTC')
        report = job['validation_report']
        self.assertIn('Atlantis', report['unmatched_countries'])
        jamaica = self.db.get(models.TourismCountry, 'JM')
        cell = service.pick(self.db, jamaica, c.TOURISM_GDP_TOTAL, 2019)
        self.assertEqual((cell['value'], cell['source'], cell['edition']), (34.5, c.WTTC, '2025 release'))
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'BS'), c.TOURISM_EMPLOYMENT, 2019)['value'], 50.2)
        self.assertGreaterEqual(job['rejected_count'], 3)  # Atlantis x2, "abc", duplicate with a different value

    def test_xlsx_import_long_layout(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['Country', 'Year', 'Indicator', 'Value'])
        sheet.append(['Spain', 2019, 'Total contribution of travel & tourism to GDP (% of GDP)', 14.3])
        sheet.append(['Spain', 2019, 'Total contribution of travel & tourism to employment (% of employment)', 14.5])
        buffer = io.BytesIO()
        workbook.save(buffer)
        job = service.import_wttc(self.db, file_name='wttc.xlsx', content=buffer.getvalue(), edition='2024 edition')
        self.assertEqual(job['success_count'], 2)
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'ES'), c.TOURISM_EMPLOYMENT, 2019)['value'], 14.5)

    def test_direct_only_columns_and_job_counts_are_rejected(self):
        csv_text = 'Country,Year,Direct contribution of travel & tourism to GDP (% of GDP),Jobs in travel & tourism (thousands)\nJamaica,2019,10,300\n'
        job = service.import_wttc(self.db, file_name='direct.csv', content=csv_text.encode(), edition='x')
        self.assertEqual(job['success_count'], 0)
        self.assertEqual(self.db.query(models.TourismObservation).filter_by(data_source=c.WTTC).count(), 0)

    def test_fraction_unit_is_converted_and_out_of_range_shares_are_rejected(self):
        csv_text = 'Country,Year,Total travel & tourism contribution to GDP (% of GDP)\nJamaica,2019,0.345\n'
        job = service.import_wttc(self.db, file_name='frac.csv', content=csv_text.encode(), edition='e', unit='fraction')
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'JM'), c.TOURISM_GDP_TOTAL, 2019)['value'], 34.5)
        bad = service.import_wttc(self.db, file_name='bad.csv', content='Country,Year,Total travel & tourism contribution to GDP (% of GDP)\nJapan,2019,340\n'.encode(), edition='e')
        self.assertEqual(bad['success_count'], 0)
        warn = service.import_wttc(self.db, file_name='w.csv', content='Country,Year,Total travel & tourism contribution to GDP (% of GDP)\nSpain,2019,0.14\n'.encode(), edition='e2')
        self.assertTrue(warn['validation_report']['warnings'])

    def test_imported_total_gdp_share_never_replaces_the_receipts_ratio(self):
        service.import_wttc(self.db, file_name='wttc.csv', content=self.CSV_WIDE.encode(), edition='e')
        row = service.compare(self.db, ['JM'], 2019)['rows'][0]['indicators']
        self.assertEqual(row[c.TOURISM_GDP_TOTAL]['value'], 34.5)
        self.assertEqual(row[c.TOURISM_DEPENDENCY]['value'], 20.0)
        self.assertEqual(row[c.TOURISM_DEPENDENCY]['source'], c.CALCULATED)

    def test_unsupported_file_type(self):
        with self.assertRaises(ValueError):
            wttc.parse('data.pdf', b'x')


class UnsdTests(DatabaseCase):
    """UN SDG API provider: series ST_GDP_ZS (SDG 8.9.1, tourism DIRECT GDP) -> TOURISM_GDP_DIRECT_PCT."""

    def test_record_normalization(self):
        row = unsd.normalize_record(un_record('388', 'Jamaica', 2019, '9.8', footnotes=('Estimate', '')))
        self.assertEqual((row['m49'], row['year'], row['value_text'], row['units'], row['nature'], row['agency']), ('388', 2019, '9.8', 'PERCENT', 'CA', 'National Statistics Office'))
        self.assertEqual(row['footnotes'], ['Estimate'])
        self.assertEqual(row['reporting_type'], 'G')
        self.assertIsNone(unsd.normalize_record(un_record('388', 'Jamaica', 2019, None)))
        self.assertIsNone(unsd.normalize_record(un_record('388', 'Jamaica', 2019, '')))
        self.assertIsNone(unsd.normalize_record({'geoAreaCode': '1', 'timePeriodStart': 'abc', 'value': '1'}))

    def test_pagination_follows_every_page(self):
        calls = []

        def fake(url, params=None, **kwargs):
            calls.append(params['page'])
            return fake_unsd(url, params)

        with mock.patch.object(http, 'get_json', fake), mock.patch.object(unsd, 'PAGE_SIZE', 3):
            rows, stats = unsd.fetch_series_rows()
        self.assertEqual(calls, [1, 2, 3, 4])
        self.assertEqual((stats['total'], stats['pages'], stats['dropped']), (10, 4, 1))  # the Turkiye record has no value
        self.assertEqual(len(rows), 9)

    def test_empty_series_is_an_error_not_silence(self):
        with mock.patch.object(http, 'get_json', lambda *a, **k: {'size': 25, 'totalElements': 0, 'totalPages': 0, 'pageNumber': 1, 'data': []}):
            with self.assertRaises(http.ProviderError):
                unsd.fetch_series_rows()

    def test_area_without_observations_is_empty_and_unknown_area_is_an_error(self):
        self.assertEqual(unsd.fetch_area('52'), [])
        with mock.patch.object(http, 'get_json', side_effect=http.ProviderError('500')):
            with self.assertRaises(http.ProviderError):
                unsd.fetch_area('999999')

    def test_m49_mapping_matches_countries_and_ignores_aggregates(self):
        report = registry.assign_m49(self.db, [{'code': a['geoAreaCode'], 'name': a['geoAreaName']} for a in UN_AREAS])
        codes = {row.country_id: row.un_m49 for row in self.db.query(models.TourismCountry) if row.un_m49}
        self.assertEqual({k: codes[k] for k in ('JM', 'BB', 'BS', 'US', 'CO', 'ES', 'JP', 'TR')},
                         {'JM': '388', 'BB': '52', 'BS': '44', 'US': '840', 'CO': '170', 'ES': '724', 'JP': '392', 'TR': '792'})
        self.assertEqual(report['unmatched_areas'], ['Grenada', 'World', 'Europe'])  # Grenada is not in this test registry; World and Europe are aggregates
        self.assertEqual(report['conflicts'], [])

    def test_shared_names_resolve_through_the_m49_overrides(self):
        areas = [{'code': '827', 'name': 'United Kingdom'}, {'code': '826', 'name': 'United Kingdom of Great Britain and Northern Ireland'}, {'code': '57', 'name': 'Micronesia'},
                 {'code': '583', 'name': 'Micronesia (Federated States of)'}]
        self.db.add(models.TourismCountry(country_id='GB', country_name='United Kingdom', iso_alpha2='GB', iso_alpha3='GBR', region='Europe', territory_status='country', in_world_bank=True, created_at='x'))
        self.db.add(models.TourismCountry(country_id='FM', country_name='Micronesia, Fed. Sts.', iso_alpha2='FM', iso_alpha3='FSM', region='Oceania', territory_status='country', in_world_bank=True, created_at='x'))
        self.db.commit()
        report = registry.assign_m49(self.db, areas)
        self.assertEqual((self.db.get(models.TourismCountry, 'GB').un_m49, self.db.get(models.TourismCountry, 'FM').un_m49), ('826', '583'))
        self.assertEqual(report['conflicts'], [])

    def test_direct_gdp_is_stored_with_full_provenance(self):
        result = service.sync_unsd(self.db, force=True)
        self.assertEqual(result['countries'], 6)  # Jamaica, Bahamas, United States, Colombia, Spain, Japan (Barbados reports nothing; World and Europe are aggregates)
        jamaica = self.db.get(models.TourismCountry, 'JM')
        cell = service.pick(self.db, jamaica, c.TOURISM_GDP_DIRECT, None)
        self.assertEqual((cell['value'], cell['year'], cell['source']), (9.8, 2019, c.UNSD))
        self.assertTrue(cell['url'].endswith('/Series/ST_GDP_ZS/GeoArea/388/DataSlice'))
        self.assertIn('ST_GDP_ZS', cell['dataset'])
        self.assertIn('not the total contribution', cell['note'])
        self.assertIn('National Statistics Office', cell['note'])
        self.assertIn('TDGVA used as proxy', cell['note'])
        self.assertTrue(cell['retrieved_at'])
        bahamas = service.pick(self.db, self.db.get(models.TourismCountry, 'BS'), c.TOURISM_GDP_DIRECT, None)
        self.assertEqual((bahamas['value'], bahamas['year'], bahamas['status']), (15.16544, 2012, c.ESTIMATED))

    def test_direct_and_total_are_separate_columns_and_never_substituted(self):
        data = service.compare(self.db, ['JM', 'ES'], 2019)
        rows = {row['iso_alpha2']: row['indicators'] for row in data['rows']}
        self.assertEqual(rows['JM'][c.TOURISM_GDP_DIRECT]['value'], 9.8)
        self.assertIsNone(rows['JM'][c.TOURISM_GDP_TOTAL]['value'])  # nothing from WTTC: the direct value must not fill the total
        self.assertIn('not a substitute', rows['JM'][c.TOURISM_GDP_TOTAL]['reason'])
        service.import_wttc(self.db, file_name='w.csv', content='Country,Year,Total travel & tourism contribution to GDP (% of GDP)\nJamaica,2019,34.5\n'.encode(), edition='e')
        rows = {row['iso_alpha2']: row['indicators'] for row in service.compare(self.db, ['JM'], 2019)['rows']}
        self.assertEqual((rows['JM'][c.TOURISM_GDP_DIRECT]['value'], rows['JM'][c.TOURISM_GDP_DIRECT]['source']), (9.8, c.UNSD))
        self.assertEqual((rows['JM'][c.TOURISM_GDP_TOTAL]['value'], rows['JM'][c.TOURISM_GDP_TOTAL]['source']), (34.5, c.WTTC))

    def test_source_priority_configuration(self):
        self.assertEqual(c.INDICATORS[c.TOURISM_GDP_DIRECT].source_priority, (c.UNSD,))
        self.assertEqual(c.INDICATORS[c.TOURISM_GDP_TOTAL].source_priority[0], c.WTTC)
        self.assertNotIn(c.WTTC, c.INDICATORS[c.TOURISM_GDP_DIRECT].source_priority)
        self.assertNotIn(c.UNSD, c.INDICATORS[c.TOURISM_GDP_TOTAL].source_priority)
        # an observation of the wrong source is ignored even if it is stored under the right indicator
        jamaica = self.db.get(models.TourismCountry, 'JM')
        service.upsert_observation(self.db, country=jamaica, indicator_code=c.TOURISM_GDP_DIRECT, year=2019, value_text='20', source=c.WTTC, dataset='x', url=None)
        service.upsert_observation(self.db, country=jamaica, indicator_code=c.TOURISM_GDP_TOTAL, year=2019, value_text='9.8', source=c.UNSD, dataset='x', url=None)
        self.db.commit()
        self.assertIsNone(service.pick(self.db, jamaica, c.TOURISM_GDP_DIRECT, 2019)['value'])
        self.assertIsNone(service.pick(self.db, jamaica, c.TOURISM_GDP_TOTAL, 2019)['value'])

    def test_missing_observations_are_na_with_a_reason(self):
        service.compare(self.db, ['BB'], None)
        barbados = service.pick(self.db, self.db.get(models.TourismCountry, 'BB'), c.TOURISM_GDP_DIRECT, None)
        self.assertIsNone(barbados['value'])
        self.assertIn('ST_GDP_ZS', barbados['reason'])
        row = service.compare(self.db, ['JM'], 2010)['rows'][0]['indicators'][c.TOURISM_GDP_DIRECT]
        self.assertIsNone(row['value'])
        self.assertIn('2018', row['reason'])  # available years are named, no other year is borrowed
        territory = registry.add_manual_country(self.db, name='Anguilla', iso2='AI', iso3=None, region='Caribbean', territory=True, parent='GB')
        self.assertIn('M49', service.pick(self.db, territory, c.TOURISM_GDP_DIRECT, None)['reason'])

    def test_historical_series(self):
        series = service.history(self.db, 'JM', 2018, 2019)['series'][c.TOURISM_GDP_DIRECT]
        self.assertEqual([(p['year'], p['value'], p['source']) for p in series], [(2018, 9.2, c.UNSD), (2019, 9.8, c.UNSD)])
        self.assertEqual(service.history(self.db, 'JM', 2019, 2019)['series'][c.TOURISM_GDP_DIRECT][0]['year'], 2019)

    def test_wrong_unit_and_duplicate_reporting_types(self):
        records = [un_record('388', 'Jamaica', 2019, '9.8'), un_record('388', 'Jamaica', 2019, '11.1', reporting='N'), un_record('44', 'Bahamas', 2012, '15', units='PERCENT_CHANGE')]
        with mock.patch.object(unsd, 'fetch_series_rows', lambda: ([unsd.normalize_record(r) for r in records], {'total': 3, 'pages': 1, 'dropped': 0})):
            result = service.sync_unsd(self.db, force=True)
        self.assertEqual(self.db.get(models.TourismCountry, 'JM').country_id, 'JM')
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'JM'), c.TOURISM_GDP_DIRECT, 2019)['value'], 9.8)  # the global-monitoring record wins
        self.assertIsNone(service.pick(self.db, self.db.get(models.TourismCountry, 'BS'), c.TOURISM_GDP_DIRECT, None)['value'])
        self.assertTrue(any('PERCENT_CHANGE' in warning for warning in result['warnings']))

    def test_out_of_range_share_requires_review(self):
        records = [un_record('388', 'Jamaica', 2019, '140')]
        with mock.patch.object(unsd, 'fetch_series_rows', lambda: ([unsd.normalize_record(r) for r in records], {'total': 1, 'pages': 1, 'dropped': 0})):
            service.sync_unsd(self.db, force=True)
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'JM'), c.TOURISM_GDP_DIRECT, 2019)['status'], c.REQUIRES_REVIEW)

    def test_provider_failure_keeps_stored_data_and_reports_it(self):
        service.sync_unsd(self.db, force=True)

        def boom(*args, **kwargs):
            raise http.ProviderError('down')

        with mock.patch.object(http, 'get_json', boom):
            result = service.sync_unsd(self.db, force=True)
        self.assertTrue(any('UN SDG API unavailable' in warning for warning in result['warnings']))
        self.assertEqual(self.db.get(models.TourismProvider, c.UNSD).connection_status, 'error')
        self.assertEqual(service.pick(self.db, self.db.get(models.TourismCountry, 'JM'), c.TOURISM_GDP_DIRECT, None)['value'], 9.8)

    def test_a_recent_sync_is_not_repeated(self):
        service.sync_unsd(self.db, force=True)
        with mock.patch.object(http, 'get_json', side_effect=AssertionError('must not be called')):
            self.assertTrue(service.sync_unsd(self.db)['skipped'])

    def test_legacy_indicator_code_is_migrated_to_the_total(self):
        jamaica = self.db.get(models.TourismCountry, 'JM')
        self.db.add(models.TourismObservation(country_id='JM', indicator_code='TOURISM_GDP', value=30.0, value_text='30', unit='%', reference_year=2019, data_source=c.WTTC,
                                              data_retrieved_at='x', dataset_edition='old', data_quality_status='Verified'))
        self.db.commit()
        service.ensure_providers(self.db)
        self.assertEqual(self.db.query(models.TourismObservation).filter_by(country_id='JM', indicator_code=c.TOURISM_GDP_TOTAL).count(), 1)
        self.assertEqual(self.db.query(models.TourismObservation).filter_by(indicator_code='TOURISM_GDP').count(), 0)
        self.assertEqual(jamaica.country_id, 'JM')


class ExportAndApiTests(DatabaseCase):
    def test_exports_hold_all_five_indicators_with_provenance(self):
        data = service.compare(self.db, ['JM', 'BB'], 2019)
        columns, records = exporter.wide_rows(data['rows'])
        for code in c.DISPLAY_INDICATORS:
            self.assertIn(f'{code}_value', columns)
            self.assertIn(f'{code}_source', columns)
        self.assertIn('TOURISM_GDP_DIRECT_PCT_value', columns)
        self.assertIn('TOURISM_GDP_TOTAL_PCT_value', columns)
        content, media, ext = exporter.render(columns, records, 'csv')
        self.assertIn(b'TOURISM_RECEIPTS_year', content)
        content, _, _ = exporter.render(columns, records, 'xlsx')
        self.assertTrue(content.startswith(b'PK'))
        long_columns, long = exporter.long_rows(self.db, data['rows'], None, None)
        self.assertTrue(all(row['data_source'] and row['data_retrieved_at'] for row in long))
        self.assertIn('data_quality_status', long_columns)

    def test_api_validation_and_responses(self):
        app = FastAPI()
        app.include_router(tourism_router.router)
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)
        self.assertEqual(client.get('/tourism/compare', params={'countries': 'JM,BB', 'year': '2019'}).status_code, 200)
        self.assertEqual(client.get('/tourism/compare', params={'countries': 'JM', 'year': '19'}).json()['detail']['code'], 'invalid_year')
        self.assertEqual(client.get('/tourism/compare', params={'countries': 'JM;DROP'}).json()['detail']['code'], 'invalid_country_code')
        self.assertEqual(client.get('/tourism/countries/ZZ').json()['detail']['code'], 'unknown_country')
        self.assertEqual(client.get('/tourism/history', params={'country': 'JM', 'from': 2020, 'to': 2010}).json()['detail']['code'], 'invalid_range')
        body = {'provider': 'WTTC', 'file_name': 'a.csv', 'content_base64': base64.b64encode(WttcImportTests.CSV_WIDE.encode()).decode(), 'dataset_edition': 'e'}
        self.assertEqual(client.post('/tourism/import', json=body).json()['success_count'] > 0, True)
        self.assertEqual(client.post('/tourism/import', json={**body, 'provider': 'STATISTA'}).status_code, 422)
        self.assertEqual(client.get('/tourism/export', params={'countries': 'JM', 'year': '2019', 'format': 'json'}).status_code, 200)
        status = client.get('/tourism/providers/status').json()['providers']
        self.assertEqual({p['provider_id'] for p in status}, {'WORLD_BANK', 'IDB', 'WTTC', 'STATISTA', 'UNSD'})

    def test_idb_and_statista_without_registry_report_not_configured(self):
        status = {p['provider_id']: p for p in service.providers_status(self.db)}
        self.assertEqual(status['IDB']['connection_status'], 'not_configured')
        self.assertIn(status['STATISTA']['connection_status'], ('disabled', 'not_configured'))
        self.assertEqual(service.sync_registered(self.db, c.IDB)['stored'], 0)


if __name__ == '__main__':
    unittest.main()
