from datetime import date, datetime
from pathlib import Path
from unittest import mock

import pytest

from backend.fuel_prices import models as m, service
from backend.fuel_prices.sources.bts_monthly import BtsMonthlyAdapter, parse
from backend.routers.fuel_prices import bts_monthly
from backend.tests.test_fuel_prices import make_db

FIXTURE = Path(__file__).parent / 'fixtures' / 'bts_monthly.html'


def test_published_system_price_and_scope():
    rows = parse(FIXTURE.read_text(encoding='utf-8'))
    assert len(rows) == 2  # YTD is excluded
    assert rows[-1].obs_date == date(2026, 9, 1)
    assert rows[-1].value_usd_per_gal == 3.86
    assert rows[-1].price_basis == 'airline_paid'
    assert rows[-1].operator_class == 'scheduled'
    assert rows[-1].raw_ref['cost_usd_millions'] == 5900.0


@pytest.mark.parametrize('text', [
    '<html>Service unavailable</html>',
    '<h1>U.S. Carriers - Scheduled</h1><tr><td>2026</td><td>September</td><td>3.86</td></tr>',
])
def test_changed_page_fails_closed(text):
    with pytest.raises(ValueError):
        parse(text)


def test_invalid_price_rejected():
    with pytest.raises(ValueError):
        parse(FIXTURE.read_text(encoding='utf-8').replace('3.86', 'NaN'))


def test_refresh_idempotence_disabled_source_and_monthly_freshness():
    db = make_db()
    try:
        assert bts_monthly(db)['status'] == 'disabled'
        service.set_enabled(db, 'bts_p12', True, 'test')
        assert bts_monthly(db)['status'] == 'no_data'
        rows = parse(FIXTURE.read_text(encoding='utf-8'))
        with mock.patch.object(BtsMonthlyAdapter, 'fetch', return_value=rows):
            assert service.refresh_source(db, 'bts_p12')['inserted'] == 2
            result = service.refresh_source(db, 'bts_p12')
            assert result['inserted'] == result['updated'] == 0
        assert bts_monthly(db)['value'] == 3.86
        source = db.get(m.FuelSource, 'bts_p12')
        run = db.get(m.FuelJobRun, ('bts_p12', 'monthly_summary'))
        now = datetime(2026, 11, 9)
        run.last_success_at = now
        run.last_attempt_at = now
        assert service._job_status(source, run, 'daily', date(2026, 9, 1), rows[0].series_id, now.date(), now)[0] == 'ok'
        service.set_enabled(db, 'bts_p12', False)
        assert bts_monthly(db)['status'] == 'disabled'
    finally:
        db.close()
