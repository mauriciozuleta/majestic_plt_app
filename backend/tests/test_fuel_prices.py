"""Tests of the aviation fuel price module. No test touches the network: adapters are fed saved text, the database is in memory."""

import math
import os
import unittest
from unittest import mock

import httpx
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.fuel_prices import models as m
from backend.fuel_prices import resolve, service, stats, units
from backend.fuel_prices.sources import bts_p12, bts_socrata, csv_import, eia_api, iata_regional
from backend.fuel_prices.stats import descriptive, drivers
from backend.fuel_prices.stats.common import Refused

def eia_rows(pairs, units='$/GAL'):
    """Rows shaped like api.eia.gov/v2 responses (period + value as a string + units)."""
    return [{'period': d, 'value': str(v) if v is not None else None, 'units': units} for d, v in pairs]


JET_ROWS = eia_rows([('2026-11-02', 3.10), ('2026-11-03', None), ('2026-11-04', 3.30)])


def make_db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service.seed(db)
    return db


def enable_all(db):
    for s in db.query(m.FuelSource).all():
        if s.adapter not in ('platts_stub', 'argus_stub', 'airnav_stub') and s.terms_status != 'restricted':
            s.enabled = True
    db.commit()


class UnitTests(unittest.TestCase):
    def test_conversions(self):
        self.assertAlmostEqual(units.to_usd_per_gal(126, 'usd_bbl'), 3.0)
        self.assertAlmostEqual(units.to_usd_per_gal(250, 'cts_gal'), 2.5)
        self.assertAlmostEqual(units.to_usd_per_gal(1.0, 'usd_litre'), 3.785411784)
        self.assertAlmostEqual(units.to_usd_per_gal(7.9 * 42 * 2, 'usd_mt', bbl_per_mt=7.9), 2.0)
        self.assertAlmostEqual(units.to_usd_per_gal(1000, 'local_per_litre', fx_to_usd=0.00025), 0.25 * 3.785411784)

    def test_no_silent_conversion(self):
        with self.assertRaises(units.UnitError):
            units.to_usd_per_gal(1000, 'local_per_litre')
        with self.assertRaises(units.UnitError):
            units.to_usd_per_gal(1, 'furlongs')


class AdapterTests(unittest.TestCase):
    def test_eia_parse_skips_missing_and_converts(self):
        jet = eia_api.parse_rows('jet_daily', JET_ROWS)
        self.assertEqual([o.obs_date.day for o in jet], [2, 4])
        self.assertEqual((jet[0].geo_level, jet[0].country_iso2, jet[0].operator_class, jet[0].price_basis, jet[0].series_id),
                         ('country', 'US', 'scheduled', 'spot', 'eia_api:EER_EPJK_PF4_RGC_DPG:daily'))
        brent = eia_api.parse_rows('brent_daily', eia_rows([('2026-03-04', 126.0)], '$/BBL'))
        self.assertAlmostEqual(brent[0].value_usd_per_gal, 3.0)
        self.assertEqual((brent[0].series_kind, brent[0].driver_code, brent[0].unit_original), ('driver', 'brent', 'usd_bbl'))
        monthly = eia_api.parse_rows('jet_monthly', eia_rows([('2026-03', 3.1)]))
        self.assertEqual((monthly[0].obs_date, monthly[0].period_type), (date(2026, 3, 1), 'month'))
        stocks = eia_api.parse_rows('jet_stocks', eia_rows([('2026-10-30', 41000)], 'MBBL'))
        self.assertTrue(stocks[0].is_native_driver)
        self.assertEqual((stocks[0].value_native, stocks[0].native_unit), (41000.0, 'mbbl'))
        with self.assertRaises(eia_api.EiaError):
            eia_api.parse_rows('jet_stocks', eia_rows([('2026-10-30', 1)], 'FURLONGS'))

    def test_eia_pagination_uses_offsets_until_total(self):
        calls = []

        def fake(route, params, tries=4):
            calls.append(params['offset'])
            n = min(5000, 12000 - params['offset'])
            return {'total': '12000', 'data': eia_rows([('2000-01-01', 1.0)] * n)}
        with mock.patch.object(eia_api, '_request', fake), mock.patch.object(eia_api.time, 'sleep'):
            rows = eia_api.fetch_rows('petroleum/pri/spt', 'X', 'daily')
        self.assertEqual((calls, len(rows)), ([0, 5000, 10000], 12000))

    def test_eia_incremental_start_param_and_job_catalogue(self):
        seen = {}

        def fake(route, params, tries=4):
            seen.update(params)
            return {'total': '0', 'data': []}
        with mock.patch.object(eia_api, '_request', fake):
            eia_api.fetch_rows('petroleum/pri/spt', 'X', 'monthly', date(2026, 5, 3))
        self.assertEqual(seen['start'], '2026-05')
        jobs = {j.key: j.frequency for j in eia_api.EiaApiAdapter().jobs()}
        self.assertEqual((jobs['jet_daily'], jobs['jet_weekly'], jobs['jet_monthly'], jobs['jet_stocks']), ('daily', 'weekly', 'monthly', 'weekly'))
        self.assertEqual(len(jobs), 11)

    def test_eia_key_never_leaks(self):
        secret = 'SECRETKEY123456'
        request = httpx.Request('GET', f'https://api.eia.gov/v2/x?api_key={secret}')
        failing = httpx.Response(404, request=request)
        with mock.patch.dict(os.environ, {'EIA_API_KEY': secret}), mock.patch.object(eia_api.httpx, 'get', return_value=failing):
            with self.assertRaises(eia_api.EiaError) as ctx:
                eia_api._request('petroleum/pri/spt/data', {})
        self.assertNotIn(secret, str(ctx.exception))
        self.assertNotIn(secret, repr(ctx.exception))
        with mock.patch.dict(os.environ, {'EIA_API_KEY': secret}):
            self.assertEqual(eia_api.scrub(f'boom {secret}'), 'boom <redacted>')
        with mock.patch.dict(os.environ, {'EIA_API_KEY': ''}):
            with self.assertRaises(eia_api.EiaError):
                eia_api._request('x', {})

    def test_eia_retries_with_backoff_on_429(self):
        ok = httpx.Response(200, json={'response': {'data': [], 'total': 0}}, request=httpx.Request('GET', 'https://api.eia.gov/v2/x'))
        limited = httpx.Response(429, request=httpx.Request('GET', 'https://api.eia.gov/v2/x'))
        with mock.patch.dict(os.environ, {'EIA_API_KEY': 'k'}), mock.patch.object(eia_api.httpx, 'get', side_effect=[limited, ok]), mock.patch.object(eia_api.time, 'sleep') as slept:
            self.assertEqual(eia_api._request('x', {})['total'], 0)
        self.assertTrue(slept.called)

    def test_bts_socrata_parse_annual_and_skips_part_year(self):
        cost = [{'year': '2024', 'total': '52000000000', 'large_regional_carriers': '2000000000', 'national_carriers': '3000000000', 'major_carriers': '47000000000'},
                {'year': '2026M1-6', 'total': '1', 'large_regional_carriers': '1', 'national_carriers': '1', 'major_carriers': '1'}]
        gallons = [{'year': '2024', 'total': '20000000000', 'large_regional_carriers': '1000000000', 'national_carriers': '1500000000', 'major_carriers': '17500000000'}]
        obs = bts_socrata.parse(cost, gallons)
        by = {o.series_id: o for o in obs}
        self.assertEqual(len(obs), 4)
        self.assertAlmostEqual(by['bts_socrata:US:total'].value_usd_per_gal, 2.6)
        self.assertAlmostEqual(by['bts_socrata:US:large_regional'].value_usd_per_gal, 2.0)
        major = by['bts_socrata:US:major']
        self.assertEqual((major.period_type, major.obs_date, major.quality), ('year', date(2024, 1, 1), 'derived'))

    def test_bts_generic_map_with_carrier_exclude(self):
        text = 'YEAR,MONTH,CARRIER_NAME,TOTAL_GALLONS,TOTAL_COST\n2025,3,Delta,1000,2500\n2025,3,United,1000,2700\n2025,3,All Majors,2000,5200\n'
        cmap = {'year': 'YEAR', 'month': 'MONTH', 'gallons': ['TOTAL_GALLONS'], 'cost': ['TOTAL_COST'], 'operator_class': 'scheduled', 'carrier_column': 'CARRIER_NAME',
                'carrier_exclude': ['All Majors']}
        obs, errors = bts_p12.parse(text, cmap)
        self.assertEqual((errors, len(obs)), ([], 1))
        self.assertAlmostEqual(obs[0].value_usd_per_gal, 2.6)  # without the exclude the aggregate row would double count
        self.assertTrue(obs[0].raw_ref['explicit_column_map'])
        _, errors = bts_p12.parse(text, {**cmap, 'gallons': ['NOPE']})
        self.assertIn('not in the file', errors[0])

    def test_bts_parse(self):
        text = ('YEAR,MONTH,CARRIER,SCHED_FUEL_GALLONS,SCHED_FUEL_COST,NONSCHED_FUEL_GALLONS,NONSCHED_FUEL_COST\n'
                '2024,1,AA,1000,2500,100,400\n2024,1,DL,1000,2700,0,0\n')
        obs, errors = bts_p12.parse(text)
        self.assertEqual(errors, [])
        by_cls = {o.operator_class: o for o in obs}
        self.assertAlmostEqual(by_cls['scheduled'].value_usd_per_gal, 2.6)  # (2500+2700)/2000
        self.assertAlmostEqual(by_cls['non_scheduled'].value_usd_per_gal, 4.0)
        self.assertEqual(by_cls['scheduled'].price_basis, 'airline_paid')

    def test_iata_parse_and_implied_factor(self):
        text = 'obs_date,region,usd_bbl,usd_mt\n2026-01-02,Latin America & Caribbean,100,790\n2026-01-02,Global,98,774\n'
        obs, errors, info = iata_regional.parse(text)
        self.assertEqual(errors, [])
        self.assertEqual(sorted((o.geo_level, o.region_code) for o in obs), [('global', None), ('region', 'LAC')])
        self.assertAlmostEqual(info['implied_bbl_per_mt'], 7.89, places=1)

    def test_csv_validation_rejects_bad_rows(self):
        head = 'obs_date,value,unit,geo_level,operator_class,price_basis,country_iso2,airport_iata,fx_to_usd\n'
        obs, errors = csv_import.parse(head + '2026-01-01,3.5,usd_gal,airport,non_scheduled,posted_retail,US,MIA,\n', 'manual_csv')
        self.assertEqual((len(obs), errors), (1, []))
        _, errors = csv_import.parse(head + '2026-01-01,1000,local_per_litre,country,scheduled,into_plane,CO,,\n', 'manual_csv')
        self.assertIn('fx_to_usd', errors[0])
        _, errors = csv_import.parse(head + '2026-01-01,350,usd_gal,country,scheduled,spot,US,,\n', 'manual_csv')
        self.assertIn('plausible', errors[0])
        _, errors = csv_import.parse('obs_date,value\n', 'manual_csv')
        self.assertIn('missing columns', errors[0])


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        enable_all(self.db)
        self.today = date(2026, 11, 9)
        service.upsert(self.db, eia_api.parse_rows('jet_daily', JET_ROWS))

    def test_seed_reference(self):
        self.assertEqual(self.db.get(m.FuelCountry, 'CO').region_code, 'LAC')
        self.assertEqual(self.db.get(m.FuelAirport, 'BOG').country_iso2, 'CO')
        self.assertTrue(self.db.query(m.FuelEvent).filter_by(event_date=date(2026, 2, 28)).count() == 1)

    def test_sources_start_disabled_except_verified_manual(self):
        db = make_db()
        states = {s.id: s.enabled for s in db.query(m.FuelSource)}
        self.assertFalse(states['eia_api'])
        self.assertFalse(states['iata_regional'])
        self.assertTrue(states['manual_csv'])
        with self.assertRaises(ValueError):
            service.set_enabled(db, 'eia_api', True)  # needs the user's sign-off
        service.set_enabled(db, 'eia_api', True, 'Don')
        self.assertEqual(db.get(m.FuelSource, 'eia_api').terms_signed_off_by, 'Don')
        with self.assertRaises(ValueError):
            service.set_enabled(db, 'airnav_stub', True, 'Don')  # restricted

    def test_acceptance_a_us_airport_and_country(self):
        for kw in ({'airport': 'MIA'}, {'country': 'US'}):
            res = resolve.get_price(self.db, today=self.today, **kw)['results']['scheduled']
            self.assertEqual(res['status'], 'ok')
            self.assertEqual((res['geo_level_used'], res['quality'], res['source']), ('country', 'observed', 'eia_api'))
            self.assertAlmostEqual(res['value'], 3.3)
            self.assertEqual(res['freshness_days'], 5)
        self.assertEqual(resolve.get_price(self.db, airport='MIA', today=self.today)['results']['scheduled']['geo_level_requested'], 'airport')

    def test_acceptance_b_region_fallback_and_estimate(self):
        res = resolve.get_price(self.db, country='CO', today=self.today)['results']['scheduled']
        self.assertEqual(res['status'], 'no_data')  # nothing for LAC yet
        obs, _, _ = iata_regional.parse('obs_date,region,usd_bbl\n2026-11-02,Latin America & Caribbean,126\n')
        service.upsert(self.db, obs)
        res = resolve.get_price(self.db, airport='BOG', today=self.today)['results']['scheduled']
        self.assertEqual((res['geo_level_requested'], res['geo_level_used'], res['quality']), ('airport', 'region', 'observed'))
        self.assertAlmostEqual(res['value'], 3.0)
        self.db.add(m.FuelAdjustment(country_iso2='CO', operator_class='scheduled', add_usd_per_gal=0.4, note='tax + into-plane'))
        self.db.commit()
        # an observed regional index still beats an estimate
        self.assertEqual(resolve.get_price(self.db, country='CO', today=self.today)['results']['scheduled']['quality'], 'observed')

    def test_estimate_is_flagged_and_traceable(self):
        obs, _, _ = iata_regional.parse('obs_date,region,usd_bbl\n2026-11-02,Latin America & Caribbean,126\n')
        service.upsert(self.db, obs)
        self.db.add(m.FuelAdjustment(country_iso2='CO', operator_class='non_scheduled', add_usd_per_gal=0.9, note='FBO margin'))
        self.db.commit()
        res = resolve.get_price(self.db, country='CO', operator_class='non_scheduled', today=self.today)['results']['non_scheduled']
        self.assertEqual((res['quality'], res['price_basis'], res['confidence']), ('estimated', 'estimate', 0.3))
        self.assertAlmostEqual(res['value'], 3.9)
        self.assertIn('3.0000 + CO adjustment +0.9000', res['formula'])

    def test_acceptance_c_no_retail_data_is_explicit(self):
        res = resolve.get_price(self.db, airport='MIA', operator_class='non_scheduled', today=self.today)['results']['non_scheduled']
        self.assertEqual(res['status'], 'no_retail_data')
        self.assertIsNone(res['value'])
        self.assertEqual(res['scheduled_reference']['quality'], 'observed')  # shown separately, never as the retail answer

    def test_manual_retail_is_found_at_airport_level(self):
        text = 'obs_date,value,unit,geo_level,operator_class,price_basis,country_iso2,airport_iata\n2026-11-05,6.20,usd_gal,airport,non_scheduled,posted_retail,US,MIA\n'
        self.assertTrue(service.import_csv(self.db, text)['ok'])
        res = resolve.get_price(self.db, airport='MIA', operator_class='non_scheduled', today=self.today)['results']['non_scheduled']
        self.assertEqual((res['geo_level_used'], res['price_basis'], res['quality']), ('airport', 'posted_retail', 'manual'))

    def test_acceptance_d_disabling_a_source_removes_its_data(self):
        service.set_enabled(self.db, 'eia_api', False)
        res = resolve.get_price(self.db, country='US', today=self.today)['results']['scheduled']
        self.assertEqual(res['status'], 'no_data')
        self.assertEqual(service.series(self.db, country='US')['points'], [])
        service.set_enabled(self.db, 'iata_regional', False)
        with self.assertRaises(service.SourceDisabled):
            service.import_iata(self.db, 'obs_date,region,usd_bbl\n2026-01-02,Global,98\n')

    def test_import_is_idempotent(self):
        text = 'obs_date,value,unit,geo_level,operator_class,price_basis,country_iso2\n2026-11-05,3.5,usd_gal,country,non_scheduled,posted_retail,US\n'
        first = service.import_csv(self.db, text)
        second = service.import_csv(self.db, text)
        self.assertEqual((first['inserted'], second['inserted'], second['updated']), (1, 0, 0))
        changed = service.import_csv(self.db, text.replace('3.5', '3.6'))
        self.assertEqual((changed['inserted'], changed['updated']), (0, 1))

    def test_change_vs_previous_periods(self):
        pts = eia_api.parse_rows('jet_daily', eia_rows([('2026-10-02', 3.0), ('2026-11-02', 3.3)]))
        service.upsert(self.db, pts)
        res = resolve.get_price(self.db, country='US', today=self.today)['results']['scheduled']
        self.assertAlmostEqual(res['changes']['1m']['pct'], 10.0, places=1)


def series(values, start=date(2020, 1, 6), step=7):
    return [(start + timedelta(days=step * i), v) for i, v in enumerate(values)]


class StatsTests(unittest.TestCase):
    def test_descriptive_known_values(self):
        out = descriptive.descriptive(series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
        self.assertAlmostEqual(out['mean'], 5.5)
        self.assertAlmostEqual(out['median'], 5.5)
        self.assertAlmostEqual(out['std'], 3.02765, places=4)
        self.assertEqual((out['min']['value'], out['max']['value'], out['n']), (1, 10, 10))

    def test_refuses_thin_data(self):
        with self.assertRaises(Refused):
            descriptive.descriptive(series([1, 2, 3]))
        with self.assertRaises(Refused):
            descriptive.volatility(series([1.0 + i * 0.01 for i in range(10)]))

    def test_volatility_known_answer_and_shock_split(self):
        # alternating +10% / -10%/(1.1) log-returns of +-a: weekly vol = a * sqrt(n/(n-1)) ~ a
        a, vals = 0.05, [100.0]
        for i in range(60):
            vals.append(vals[-1] * math.exp(a if i % 2 == 0 else -a))
        out = descriptive.volatility(series(vals), event_dates=[series(vals)[10][0]], shock_weeks=8)
        self.assertAlmostEqual(out['weekly_vol'], a, delta=0.002)
        self.assertAlmostEqual(out['annualized_vol'], a * math.sqrt(52), delta=0.02)
        self.assertGreaterEqual(out['shock']['n'], 5)

    def test_seasonality_recovers_a_known_pattern(self):
        pts = []
        for year in range(2018, 2024):
            for month in range(1, 13):
                effect = 0.10 if month == 7 else (-0.10 if month == 1 else 0.0)
                pts.append((date(year, month, 1), math.exp(math.log(2.0) + effect)))
        out = descriptive.seasonality(pts)
        by_month = {r['month']: r for r in out['months']}
        self.assertGreater(by_month[7]['effect_pct'], 8)
        self.assertLess(by_month[1]['effect_pct'], -8)
        self.assertEqual(out['complete_years'], 6)
        self.assertNotIn('warning', out)

    def test_seasonality_flags_short_history(self):
        pts = [(date(2022 + (i // 12), i % 12 + 1, 1), 2.0 + 0.01 * (i % 12)) for i in range(36)]
        self.assertIn('warning', descriptive.seasonality(pts))
        self.assertEqual(descriptive.seasonality(pts[:24])['complete_years'], 2)
        with self.assertRaises(Refused):
            descriptive.seasonality(pts[:23])

    def test_regression_exact_line(self):
        b = series([2 + 0.1 * i + (0.3 if i % 3 == 0 else 0) for i in range(60)])
        j = [(d, 2.0 * v + 1.0) for d, v in b]
        out = drivers.regression(j, b)
        self.assertAlmostEqual(out['levels']['slope'], 2.0, places=6)
        self.assertAlmostEqual(out['levels']['intercept'], 1.0, places=6)
        self.assertAlmostEqual(out['levels']['r2'], 1.0, places=6)

    def test_lagged_correlation_finds_the_lead(self):
        import random
        rnd = random.Random(1)
        shocks = [rnd.gauss(0, 0.03) for _ in range(120)]
        brent, jet = [100.0], [100.0]
        for i in range(1, 120):
            brent.append(brent[-1] * math.exp(shocks[i]))
            jet.append(jet[-1] * math.exp(shocks[i - 2] if i >= 2 else 0.0))  # jet follows Brent by 2 weeks
        out = drivers.lagged_correlations(series(jet), series(brent))
        self.assertEqual(out['best']['lag_weeks'], 2)
        self.assertGreater(out['best']['corr'], 0.95)
        self.assertEqual(out['lags_tested_weeks'][0], -4)

    def test_half_life_of_a_known_ar1(self):
        import random
        rnd = random.Random(7)
        phi, x, vals = 0.9, 0.5, []
        for _ in range(1500):  # seeded AR(1) around 0.5; a long sample so the estimate is tight
            x = 0.5 + phi * (x - 0.5) + rnd.gauss(0, 0.05)
            vals.append(x)
        out = drivers.half_life(series(vals))
        self.assertAlmostEqual(out['phi'], phi, delta=0.03)
        self.assertAlmostEqual(out['half_life_weeks'], math.log(0.5) / math.log(0.9), delta=1.5)
        self.assertAlmostEqual(out['long_run_mean'], 0.5, delta=0.1)
        self.assertIsNone(drivers.half_life(series([0.5 + 0.01 * i for i in range(60)]))['half_life_weeks'])  # a trend does not mean-revert

    def test_decomposition_matches_the_2026_eia_example(self):
        # jet roughly doubles over the spring while the crack spread goes 0.42 -> 1.25 USD/gal (EIA, as quoted by the user)
        days = [date(2026, 1, 2) + timedelta(days=i) for i in range(0, 150, 5)]
        n = len(days) - 1
        brent = [2.10 + (1.40 * i / n) for i in range(len(days))]
        crack = [0.42 + (1.25 - 0.42) * i / n for i in range(len(days))]
        jet = [b + c for b, c in zip(brent, crack)]
        out = drivers.decomposition(list(zip(days, jet)), list(zip(days, brent)))
        self.assertAlmostEqual(out['start']['crack'], 0.42)
        self.assertAlmostEqual(out['end']['crack'], 1.25)
        self.assertAlmostEqual(out['delta']['jet'], out['delta']['crude'] + out['delta']['crack'])
        self.assertAlmostEqual(out['share_of_change']['crude'] + out['share_of_change']['crack'], 1.0)
        self.assertAlmostEqual(out['delta']['crack'], 0.83)
        self.assertGreater(out['share_of_change']['crude'], 0.55)

    def test_pass_through_and_retail_premium(self):
        months = [date(2021 + (i // 12), i % 12 + 1, 1) for i in range(36)]
        spot = [(d, 2.0 + 0.5 * math.sin(i / 3)) for i, d in enumerate(months)]
        paid = [(months[i], spot[i - 1][1] + 0.2) for i in range(1, 36)]  # airlines pay last month's spot + 0.2
        out = drivers.pass_through(spot, paid)
        self.assertEqual(out['best']['lag_months'], 1)
        retail = [(d, v + 1.5) for d, v in spot]
        prem = drivers.retail_premium(retail, spot)
        self.assertAlmostEqual(prem['mean'], 1.5)
        with self.assertRaises(Refused):
            drivers.retail_premium(retail[:2], spot)

    def test_event_window_and_refusal(self):
        pts = series([3.0] * 6 + [4.0] * 6)
        ev = [{'date': pts[6][0], 'title': 'shock'}]
        out = drivers.event_windows(pts, ev, weeks=5)
        self.assertAlmostEqual(out['events'][0]['change_pct'], 33.3333, places=2)
        with self.assertRaises(Refused):
            drivers.event_windows(pts, [{'date': date(2010, 1, 1), 'title': 'old'}], weeks=4)

    def test_compute_refuses_without_data_and_reports_quality(self):
        db = make_db()
        enable_all(db)
        res = stats.compute(db, 'descriptive', country='US')
        self.assertEqual(res['status'], 'refused')
        days = [date(2025, 1, 1) + timedelta(days=i) for i in range(30)]
        service.upsert(db, eia_api.parse_rows('jet_daily', eia_rows([(d.isoformat(), 2 + i * 0.01) for i, d in enumerate(days)])))
        res = stats.compute(db, 'descriptive', country='US')
        self.assertEqual((res['status'], res['n'], res['quality_mix']), ('ok', 30, {'observed': 30}))
        self.assertEqual(stats.compute(db, 'decomposition', country='US')['status'], 'refused')  # no Brent loaded
        self.assertEqual(stats.compute(db, 'inventories', country='US')['status'], 'refused')


class _FakeAdapter:
    """An automatic adapter that serves canned rows (or fails) so scheduling can be tested without the network."""
    automatic = True
    fail = False
    calls: list = []

    def jobs(self):
        from backend.fuel_prices.sources.base import Job
        return [Job('daily_jet', 'daily', 'jet', 'eia_api:EER_EPJK_PF4_RGC_DPG:daily'), Job('weekly_stocks', 'weekly', 'stocks', 'eia_api:WKJSTUS1:weekly')]

    def fetch_job(self, key, since=None):
        _FakeAdapter.calls.append((key, since))
        if _FakeAdapter.fail:
            raise eia_api.EiaError('HTTP 503 from petroleum/pri/spt/data')
        if key == 'daily_jet':
            return eia_api.parse_rows('jet_daily', eia_rows([('2026-11-03', 4.1), ('2026-11-04', 4.2)]))
        return eia_api.parse_rows('jet_stocks', eia_rows([('2026-10-30', 40000)], 'MBBL'))


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        service.set_enabled(self.db, 'eia_api', True, 'tester')
        _FakeAdapter.fail, _FakeAdapter.calls = False, []
        self.patch = mock.patch.dict(service.ADAPTERS, {'eia_api': _FakeAdapter})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_seed_marks_fred_restricted_and_purges_its_rows(self):
        db = make_db()
        db.add(m.FuelObservation(series_id='eia_fred:X', obs_date=date(2026, 1, 1), value_usd_per_gal=3.0, geo_level='country', price_basis='spot', source_id='eia_fred'))
        db.get(m.FuelSource, 'eia_fred').terms_status = 'unverified'
        db.get(m.FuelSource, 'eia_fred').enabled = True
        db.commit()
        service.seed(db)  # what the next startup does
        fred = db.get(m.FuelSource, 'eia_fred')
        self.assertEqual((fred.terms_status, fred.enabled), ('restricted', False))
        self.assertEqual(db.query(m.FuelObservation).filter_by(source_id='eia_fred').count(), 0)
        with self.assertRaises(ValueError):
            service.set_enabled(db, 'eia_fred', True, 'Don')

    def test_seed_keeps_a_users_signoff_status(self):
        db = make_db()
        service.set_enabled(db, 'eia_api', True, 'Don')
        db.get(m.FuelSource, 'eia_api').terms_status = 'verified_ok'
        db.commit()
        service.seed(db)
        self.assertEqual(db.get(m.FuelSource, 'eia_api').terms_status, 'verified_ok')

    def test_first_run_backfills_then_runs_are_incremental_and_idempotent(self):
        first = service.refresh_source(self.db, 'eia_api')
        self.assertTrue(first['ok'])
        self.assertEqual([c[1] for c in _FakeAdapter.calls], [None, None])  # no data yet: full history
        self.assertEqual(self.db.query(m.FuelObservation).count(), 2)
        self.assertEqual(self.db.query(m.FuelDriverPoint).count(), 1)
        _FakeAdapter.calls = []
        again = service.refresh_source(self.db, 'eia_api')
        self.assertEqual((again['inserted'], again['updated']), (0, 0))
        self.assertEqual(dict(_FakeAdapter.calls)['daily_jet'], date(2026, 11, 4))  # since = newest stored point

    def test_due_logic_runs_each_job_on_its_own_frequency_and_catches_up(self):
        now = datetime(2026, 11, 9, 12, 0)
        self.assertTrue(service.job_due(None, 'daily', now))
        run = m.FuelJobRun(source_id='eia_api', job_key='j', last_success_at=now - timedelta(hours=5))
        self.assertFalse(service.job_due(run, 'daily', now))
        run.last_success_at = now - timedelta(days=1, minutes=-10)
        self.assertTrue(service.job_due(run, 'daily', now))  # within the 30 min tolerance
        self.assertFalse(service.job_due(run, 'weekly', now))
        run.last_success_at = now - timedelta(days=30)  # app was down for a month: everything is due at startup
        self.assertTrue(all(service.job_due(run, f, now) for f in ('daily', 'weekly', 'monthly')))

    def test_refresh_due_skips_jobs_that_are_not_due(self):
        service.refresh_due(self.db)
        _FakeAdapter.calls = []
        self.assertEqual(service.refresh_due(self.db), [])
        self.assertEqual(_FakeAdapter.calls, [])

    def test_failure_is_stored_not_raised_and_backs_off(self):
        _FakeAdapter.fail = True
        out = service.refresh_due(self.db)
        self.assertTrue(out and not any(r['ok'] for r in out))
        run = self.db.get(m.FuelJobRun, ('eia_api', 'daily_jet'))
        self.assertIn('HTTP 503', run.last_error)
        _FakeAdapter.calls = []
        self.assertEqual(service.refresh_due(self.db), [])  # retried no sooner than 6 hours later
        self.assertEqual(_FakeAdapter.calls, [])
        cov = service.coverage(self.db)
        self.assertTrue(any(j['status'] == 'error' for j in cov['jobs']))
        self.assertTrue(cov['stale'])

    def test_stale_warning_by_data_age(self):
        service.refresh_source(self.db, 'eia_api')
        fresh = service.coverage(self.db, today=date(2026, 11, 5))
        self.assertTrue(all(j['status'] == 'ok' for j in fresh['jobs']))
        old = service.coverage(self.db, today=date(2026, 12, 20))
        self.assertTrue(any(j['status'] == 'stale' and 'days old' in j['detail'] for j in old['jobs']))

    def test_native_drivers_feed_the_driver_stats_instead_of_refusing(self):
        days = [date(2024, 1, 5) + timedelta(weeks=i) for i in range(80)]
        brent = [(d.isoformat(), 70 + 10 * math.sin(i / 6)) for i, d in enumerate(days)]
        jet = [(d.isoformat(), (70 + 10 * math.sin(i / 6)) / 42 + 0.5 + 0.3 * math.sin(i / 4)) for i, d in enumerate(days)]
        stocks = [(d.isoformat(), 40000 + 2000 * math.sin(i / 4)) for i, d in enumerate(days)]
        service.upsert(self.db, eia_api.parse_rows('jet_weekly', eia_rows(jet)) + eia_api.parse_rows('brent_weekly', eia_rows(brent, '$/BBL'))
                       + eia_api.parse_rows('jet_stocks', eia_rows(stocks, 'MBBL')))
        one = stats.compute(self.db, 'inventories', country='US', driver='jet_stocks')
        self.assertEqual(one['status'], 'ok')
        self.assertEqual([r['lag_weeks'] for r in one['rows']], list(range(9)))
        many = stats.compute(self.db, 'drivers', country='US')
        by = {d['driver']: d for d in many['drivers']}
        self.assertEqual(by['jet_stocks']['status'], 'ok')
        self.assertEqual(by['jet_stocks']['unit'], 'mbbl')
        self.assertEqual(by['jet_exports']['status'], 'refused')  # that series was not loaded: refuses on its own, the rest still answer
        self.assertEqual(service.series(self.db, kind='driver', driver='jet_stocks')['unit'], 'mbbl')

    def test_attribution_reaches_price_and_series(self):
        service.refresh_source(self.db, 'eia_api')
        res = resolve.get_price(self.db, country='US', today=date(2026, 11, 5))['results']['scheduled']
        self.assertEqual(res['attribution'], 'Source: U.S. Energy Information Administration (eia.gov)')
        self.assertIn('Energy Information Administration', service.series(self.db, country='US')['attribution'])


class DropFolderTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(service, 'DROP_DIR', self.tmp)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.db = make_db()
        self.cmap = {'year': 'YEAR', 'month': 'MONTH', 'gallons': ['G'], 'cost': ['C'], 'operator_class': 'scheduled'}

    def test_disabled_source_imports_nothing(self):
        (self.tmp / 'a.csv').write_text('YEAR,MONTH,G,C\n2026,9,1000,2600\n')
        self.assertEqual(service.scan_drop_folder(self.db), [])
        self.assertTrue((self.tmp / 'a.csv').exists())

    def test_file_with_explicit_map_is_imported_then_moved(self):
        import json as _json
        service.set_enabled(self.db, 'bts_p12', True, 'Don')
        (self.tmp / 'column_map.json').write_text(_json.dumps(self.cmap))
        (self.tmp / 'a.csv').write_text('YEAR,MONTH,G,C\n2026,9,1000,2600\n2026,8,1000,2800\n')
        out = service.scan_drop_folder(self.db)
        self.assertTrue(out[0]['ok'] and out[0]['months'] == 2)
        self.assertEqual(len(list((self.tmp / 'processed').glob('*_a.csv'))), 1)
        self.assertEqual(service.scan_drop_folder(self.db), [])  # nothing left to import
        res = service.series(self.db, country='US', period='month', source_id='bts_p12')
        self.assertEqual([p['value'] for p in res['points']], [2.8, 2.6])

    def test_missing_map_or_bad_file_is_reported_and_isolated(self):
        import json as _json
        service.set_enabled(self.db, 'bts_p12', True, 'Don')
        (self.tmp / 'a.csv').write_text('YEAR,MONTH,G,C\n2026,9,1000,2600\n')
        out = service.scan_drop_folder(self.db)
        self.assertIn('column_map.json', out[0]['error'])
        self.assertTrue((self.tmp / 'a.csv').exists())  # left alone until a map exists
        (self.tmp / 'column_map.json').write_text(_json.dumps({**self.cmap, 'gallons': ['NOPE']}))
        out = service.scan_drop_folder(self.db)
        self.assertFalse(out[0]['ok'])
        self.assertTrue((self.tmp / 'failed' / 'a.csv.error.txt').exists())
        self.assertIn('a.csv', self.db.get(m.FuelSource, 'bts_p12').last_error)

    def test_monthly_reminder_appears_until_the_expected_month_is_imported(self):
        self.assertIsNone(service.bts_reminder(self.db, date(2026, 11, 9)))  # source disabled: no nagging
        service.set_enabled(self.db, 'bts_p12', True, 'Don')
        reminder = service.bts_reminder(self.db, date(2026, 11, 9))
        self.assertEqual((reminder['expected_through'], reminder['latest_imported']), ('2026-09-01', None))
        text = 'YEAR,MONTH,G,C\n2026,9,1000,2600\n'
        obs, _ = bts_p12.parse(text, self.cmap)
        service.upsert(self.db, obs)
        self.assertIsNone(service.bts_reminder(self.db, date(2026, 11, 9)))
        self.assertIsNotNone(service.bts_reminder(self.db, date(2026, 12, 20)))
        self.assertEqual(service.coverage(self.db, date(2026, 12, 20))['reminders'][0]['source'], 'bts_p12')


if __name__ == '__main__':
    unittest.main()
