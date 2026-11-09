"""Statistics layer: pure functions on (date, value) lists (descriptive.py, drivers.py) plus `compute`, which loads the canonical series from the database for the API.

Every result carries n, date range and quality mix; when the data are too thin the result is {"status": "refused", "reason": ...} instead of a number."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import models as m
from .. import service
from . import descriptive, drivers
from .common import Refused

KINDS = ('descriptive', 'volatility', 'seasonality', 'decomposition', 'regression', 'lags', 'half_life', 'inventories', 'pass_through', 'retail_premium', 'events')


def _pts(series: dict):
    return [(date.fromisoformat(p['date']), p['value']) for p in series['points']]


def compute(db: Session, kind: str, *, country: str | None = 'US', airport: str | None = None, region: str | None = None, operator_class: str = 'scheduled',
            date_from: date | None = None, date_to: date | None = None, window_days: int | None = None, weeks: int = 4, driver: str = 'jet_stocks') -> dict:
    if kind not in KINDS:
        return {'status': 'error', 'reason': f'unknown statistic {kind!r}; choose one of {", ".join(KINDS)}'}
    where = dict(country=country, airport=airport, region=region, operator_class=operator_class, date_from=date_from, date_to=date_to)
    price = service.series(db, **where)
    brent = service.series(db, kind='driver', driver='brent', date_from=date_from, date_to=date_to)
    q = price['quality_mix']
    try:
        if not price['points']:
            raise Refused('no price series for this place/class from an enabled source.')
        jet = _pts(price)
        if kind == 'descriptive':
            body = descriptive.descriptive(jet, window_days, q)
        elif kind == 'volatility':
            body = descriptive.volatility(jet, _event_dates(db), quality_mix=q)
        elif kind == 'seasonality':
            body = descriptive.seasonality(jet, q)
        elif kind == 'events':
            body = drivers.event_windows(jet, _events(db), weeks, q)
        elif kind == 'pass_through':
            paid = service.series(db, country=country, operator_class=operator_class, period='month', source_id='bts_p12', date_from=date_from, date_to=date_to)
            spot = service.series(db, country=country, operator_class='scheduled', period='month', source_id='eia_fred', date_from=date_from, date_to=date_to)
            if not paid['points'] or not spot['points']:
                raise Refused('needs both an airline-paid series (BTS P-12(a)) and a spot series (EIA) from enabled sources.')
            body = drivers.pass_through(_pts(spot), _pts(paid), paid['quality_mix'])
        elif kind == 'retail_premium':
            retail = service.series(db, country=country, airport=airport, operator_class='non_scheduled', date_from=date_from, date_to=date_to)
            spot = service.series(db, country=country, operator_class='scheduled', period='month', source_id='eia_fred', date_from=date_from, date_to=date_to)
            if not retail['points'] or not spot['points']:
                raise Refused('needs a non-scheduled retail series and a spot series; no observed retail data is loaded for this place.')
            body = drivers.retail_premium(_pts(retail), _pts(spot), retail['quality_mix'])
        else:  # everything below needs Brent
            if not brent['points']:
                raise Refused('no Brent series from an enabled source.')
            b = _brent_gal(brent)
            if kind == 'decomposition':
                body = drivers.decomposition(jet, b, date_from, date_to, q)
            elif kind == 'regression':
                body = drivers.regression(jet, b, q)
            elif kind == 'lags':
                body = drivers.lagged_correlations(jet, b, q)
            elif kind == 'half_life':
                body = drivers.half_life(drivers.crack(jet, b), q)
            else:  # inventories
                other = service.series(db, kind='driver', driver=driver, date_from=date_from, date_to=date_to)
                body = drivers.driver_relationship(drivers.crack(jet, b), _pts(other) if other['points'] else None, driver, q)
        return {'status': 'ok', 'kind': kind, 'series_id': price['series_id'], **body}
    except Refused as why:
        return {'status': 'refused', 'kind': kind, 'reason': str(why)}


def _brent_gal(brent: dict):
    return _pts(brent)  # service.series already returns the canonical USD per gallon value


def _events(db: Session):
    return [{'date': e.event_date, 'title': e.title} for e in db.query(m.FuelEvent).order_by(m.FuelEvent.event_date)]


def _event_dates(db: Session):
    return [e['date'] for e in _events(db)]
