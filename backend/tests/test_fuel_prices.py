"""Tests of the aviation fuel price module. No test touches the network: adapters are fed saved text, the database is in memory."""

import math
import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.fuel_prices import models as m
from backend.fuel_prices import resolve, service, stats, units
from backend.fuel_prices.sources import bts_p12, csv_import, eia_fred, iata_regional
from backend.fuel_prices.stats import descriptive, drivers
from backend.fuel_prices.stats.common import Refused

FRED_JET = 'observation_date,DJFUELUSGULF\n2026-03-02,3.10\n2026-03-03,.\n2026-03-04,3.30\n'
FRED_BRENT = 'observation_date,DCOILBRENTEU\n2026-03-02,84.0\n2026-03-04,126.0\n'


def make_db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service.seed(db)
    return db


def enable_all(db):
    for s in db.query(m.FuelSource).all():
        if s.adapter not in ('platts_stub', 'argus_stub', 'airnav_stub'):
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
    def test_fred_parse_skips_missing_and_converts(self):
        jet = eia_fred.parse_csv(FRED_JET, 'DJFUELUSGULF')
        self.assertEqual([o.obs_date.day for o in jet], [2, 4])
        self.assertEqual((jet[0].geo_level, jet[0].country_iso2, jet[0].operator_class, jet[0].price_basis), ('country', 'US', 'scheduled', 'spot'))
        brent = eia_fred.parse_csv(FRED_BRENT, 'DCOILBRENTEU')
        self.assertAlmostEqual(brent[1].value_usd_per_gal, 3.0)
        self.assertEqual((brent[1].series_kind, brent[1].driver_code, brent[1].unit_original), ('driver', 'brent', 'usd_bbl'))

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
        jet = eia_fred.parse_csv(FRED_JET.replace('2026-03', '2026-11'), 'DJFUELUSGULF')
        service.upsert(self.db, jet)

    def test_seed_reference(self):
        self.assertEqual(self.db.get(m.FuelCountry, 'CO').region_code, 'LAC')
        self.assertEqual(self.db.get(m.FuelAirport, 'BOG').country_iso2, 'CO')
        self.assertTrue(self.db.query(m.FuelEvent).filter_by(event_date=date(2026, 2, 28)).count() == 1)

    def test_sources_start_disabled_except_verified_manual(self):
        db = make_db()
        states = {s.id: s.enabled for s in db.query(m.FuelSource)}
        self.assertFalse(states['eia_fred'])
        self.assertFalse(states['iata_regional'])
        self.assertTrue(states['manual_csv'])
        with self.assertRaises(ValueError):
            service.set_enabled(db, 'eia_fred', True)  # needs the user's sign-off
        service.set_enabled(db, 'eia_fred', True, 'Don')
        self.assertEqual(db.get(m.FuelSource, 'eia_fred').terms_signed_off_by, 'Don')
        with self.assertRaises(ValueError):
            service.set_enabled(db, 'airnav_stub', True, 'Don')  # restricted

    def test_acceptance_a_us_airport_and_country(self):
        for kw in ({'airport': 'MIA'}, {'country': 'US'}):
            res = resolve.get_price(self.db, today=self.today, **kw)['results']['scheduled']
            self.assertEqual(res['status'], 'ok')
            self.assertEqual((res['geo_level_used'], res['quality'], res['source']), ('country', 'observed', 'eia_fred'))
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
        service.set_enabled(self.db, 'eia_fred', False)
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
        pts = [eia_fred.parse_csv('observation_date,DJFUELUSGULF\n2026-10-02,3.0\n2026-11-02,3.3\n', 'DJFUELUSGULF')][0]
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
        service.upsert(db, [o for o in eia_fred.parse_csv('observation_date,DJFUELUSGULF\n' + '\n'.join(f'{d},{2 + i * 0.01}' for i, d in enumerate(days)), 'DJFUELUSGULF')])
        res = stats.compute(db, 'descriptive', country='US')
        self.assertEqual((res['status'], res['n'], res['quality_mix']), ('ok', 30, {'observed': 30}))
        self.assertEqual(stats.compute(db, 'decomposition', country='US')['status'], 'refused')  # no Brent loaded
        self.assertEqual(stats.compute(db, 'inventories', country='US')['status'], 'refused')


if __name__ == '__main__':
    unittest.main()
