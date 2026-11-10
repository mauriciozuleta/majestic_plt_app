"""API of the aviation fuel price module (backend/fuel_prices/). Thin: everything real is in the package.

  GET  /api/fuel/sources                      registry: terms status, enabled, last success/error, observation count
  POST /api/fuel/sources/{id}/enable          {enabled, signed_off_by}  unverified sources need the user's name as sign-off
  POST /api/fuel/sources/{id}/refresh         fetch now (automatic sources only)
  GET  /api/fuel/price                        ?country=&airport=&class=scheduled|non_scheduled|both&from=&to=   resolved with provenance
  GET  /api/fuel/series                       ?country=|airport=|region=&class=&kind=price|driver&driver=brent&from=&to=
  GET  /api/fuel/stats/{kind}                 descriptive|volatility|seasonality|decomposition|regression|lags|half_life|inventories|pass_through|retail_premium|events
  GET  /api/fuel/airports/search?q=           IATA / name / city autocomplete
  GET  /api/fuel/countries                    countries with region
  GET  /api/fuel/search?q=                    one box: country name, ISO code or IATA code
  GET  /api/fuel/coverage                     what has observed data, which sources are off
  GET  /api/fuel/events, POST /api/fuel/events   shock events
  GET/POST/DELETE /api/fuel/adjustments       country adjustments used to build labelled estimates
  POST /api/fuel/import/csv | /import/iata | /import/bts   (multipart-free: JSON {text, ...})
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..fuel_prices import models as m
from ..fuel_prices import resolve, service, stats

router = APIRouter(prefix='/api/fuel', tags=['fuel'])


class EnableBody(BaseModel):
    enabled: bool
    signed_off_by: str | None = None


class ImportBody(BaseModel):
    text: str
    source_id: str = 'manual_csv'
    column_map: dict | None = None


class EventBody(BaseModel):
    event_date: date
    title: str
    category: str | None = None
    source_url: str | None = None


class AdjustmentBody(BaseModel):
    country_iso2: str
    operator_class: str
    add_usd_per_gal: float
    note: str | None = None


@router.get('/sources')
def list_sources(db: Session = Depends(get_db)):
    return service.sources_view(db)


@router.post('/sources/{source_id}/enable')
def enable_source(source_id: str, body: EnableBody, db: Session = Depends(get_db)):
    try:
        service.set_enabled(db, source_id, body.enabled, body.signed_off_by)
    except KeyError:
        raise HTTPException(404, 'unknown source')
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {'ok': True}


@router.post('/sources/{source_id}/refresh')
def refresh_source(source_id: str, full: bool = False, db: Session = Depends(get_db)):
    return service.refresh_source(db, source_id, full=full)


@router.get('/price')
def price(country: str | None = None, airport: str | None = None, cls: str = Query('scheduled', alias='class'), date_from: date | None = Query(None, alias='from'),
          date_to: date | None = Query(None, alias='to'), db: Session = Depends(get_db)):
    if cls not in ('scheduled', 'non_scheduled', 'both'):
        raise HTTPException(400, 'class must be scheduled, non_scheduled or both')
    if not country and not airport:
        raise HTTPException(400, 'give country or airport')
    return resolve.get_price(db, country=country, airport=airport, operator_class=cls, date_from=date_from, date_to=date_to)


@router.get('/bts/monthly')
def bts_monthly(db: Session = Depends(get_db)):
    """Separate U.S. airline-paid benchmark, independent of the spot-price resolver."""
    source = db.get(m.FuelSource, 'bts_p12')
    if source is None or not source.enabled:
        return {'status': 'disabled', 'message': 'Enable BTS monthly fuel in Data coverage & sources.'}
    row = (db.query(m.FuelObservation).filter_by(source_id='bts_p12', series_id='bts_p12:US:scheduled',
                                               operator_class='scheduled', period_type='month')
           .order_by(m.FuelObservation.obs_date.desc()).first())
    if row is None:
        return {'status': 'no_data', 'message': 'Monthly BTS data has not been downloaded yet.'}
    return resolve._answer(db, row, 'country', date.today())


@router.get('/series')
def series(kind: str = 'price', country: str | None = None, airport: str | None = None, region: str | None = None, cls: str = Query('scheduled', alias='class'),
           driver: str | None = None, date_from: date | None = Query(None, alias='from'), date_to: date | None = Query(None, alias='to'), db: Session = Depends(get_db)):
    return service.series(db, kind=kind, country=country, airport=airport, region=region, operator_class=cls, driver=driver, date_from=date_from, date_to=date_to)


@router.get('/stats/{kind}')
def statistic(kind: str, country: str | None = None, airport: str | None = None, region: str | None = None, cls: str = Query('scheduled', alias='class'),
              date_from: date | None = Query(None, alias='from'), date_to: date | None = Query(None, alias='to'), window_days: int | None = None, weeks: int = 4,
              driver: str = 'jet_stocks', db: Session = Depends(get_db)):
    return stats.compute(db, kind, country=country, airport=airport, region=region, operator_class=cls, date_from=date_from, date_to=date_to, window_days=window_days,
                         weeks=weeks, driver=driver)


@router.get('/airports/search')
def search_airports(q: str = Query(..., min_length=1), limit: int = 15, db: Session = Depends(get_db)):
    term = q.strip()
    rows = (db.query(m.FuelAirport).filter(or_(m.FuelAirport.iata == term.upper(), m.FuelAirport.name.ilike(f'%{term}%'), m.FuelAirport.city.ilike(f'%{term}%')))
            .order_by((m.FuelAirport.iata == term.upper()).desc(), m.FuelAirport.name).limit(limit).all())
    return [{'iata': a.iata, 'name': a.name, 'city': a.city, 'country_iso2': a.country_iso2, 'region_code': a.region_code} for a in rows]


@router.get('/countries')
def countries(db: Session = Depends(get_db)):
    return [{'iso2': c.iso2, 'name': c.name, 'region_code': c.region_code} for c in db.query(m.FuelCountry).order_by(m.FuelCountry.name)]


@router.get('/search')
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """One box: a 3-letter IATA code, a 2-letter ISO code or part of a country / airport name."""
    term = q.strip()
    out = []
    for a in db.query(m.FuelAirport).filter(or_(m.FuelAirport.iata == term.upper(), m.FuelAirport.name.ilike(f'%{term}%'), m.FuelAirport.city.ilike(f'%{term}%'))).order_by(
            (m.FuelAirport.iata == term.upper()).desc(), m.FuelAirport.name).limit(8):
        out.append({'type': 'airport', 'code': a.iata, 'label': f'{a.iata} — {a.name}, {a.city or ""} ({a.country_iso2})', 'country_iso2': a.country_iso2})
    for c in db.query(m.FuelCountry).filter(or_(m.FuelCountry.iso2 == term.upper(), m.FuelCountry.name.ilike(f'%{term}%'))).order_by(m.FuelCountry.name).limit(8):
        out.append({'type': 'country', 'code': c.iso2, 'label': f'{c.name} ({c.iso2})', 'country_iso2': c.iso2})
    out.sort(key=lambda r: (r['code'].upper() != term.upper(), r['type'] != 'country'))
    return out[:12]


@router.get('/coverage')
def coverage(db: Session = Depends(get_db)):
    return service.coverage(db)


@router.get('/events')
def list_events(db: Session = Depends(get_db)):
    return [{'id': e.id, 'date': e.event_date.isoformat(), 'title': e.title, 'category': e.category, 'source_url': e.source_url}
            for e in db.query(m.FuelEvent).order_by(m.FuelEvent.event_date)]


@router.post('/events')
def add_event(body: EventBody, db: Session = Depends(get_db)):
    if db.query(m.FuelEvent).filter_by(event_date=body.event_date, title=body.title).first():
        return {'ok': True, 'duplicate': True}
    db.add(m.FuelEvent(event_date=body.event_date, title=body.title, category=body.category, source_url=body.source_url))
    db.commit()
    return {'ok': True}


@router.get('/adjustments')
def list_adjustments(db: Session = Depends(get_db)):
    return [{'id': a.id, 'country_iso2': a.country_iso2, 'operator_class': a.operator_class, 'add_usd_per_gal': a.add_usd_per_gal, 'note': a.note} for a in db.query(m.FuelAdjustment)]


@router.post('/adjustments')
def set_adjustment(body: AdjustmentBody, db: Session = Depends(get_db)):
    if body.operator_class not in ('scheduled', 'non_scheduled'):
        raise HTTPException(400, 'operator_class must be scheduled or non_scheduled')
    row = db.query(m.FuelAdjustment).filter_by(country_iso2=body.country_iso2.upper(), operator_class=body.operator_class).first()
    if row:
        row.add_usd_per_gal, row.note = body.add_usd_per_gal, body.note
    else:
        db.add(m.FuelAdjustment(country_iso2=body.country_iso2.upper(), operator_class=body.operator_class, add_usd_per_gal=body.add_usd_per_gal, note=body.note))
    db.commit()
    return {'ok': True}


@router.delete('/adjustments/{adjustment_id}')
def delete_adjustment(adjustment_id: int, db: Session = Depends(get_db)):
    db.query(m.FuelAdjustment).filter_by(id=adjustment_id).delete()
    db.commit()
    return {'ok': True}


def _run_import(fn, *args):
    try:
        result = fn(*args)
    except service.SourceDisabled as exc:
        raise HTTPException(409, str(exc))
    except KeyError:
        raise HTTPException(404, 'unknown source')
    if not result.get('ok'):
        raise HTTPException(422, result)
    return result


@router.post('/import/csv')
def import_csv(body: ImportBody, db: Session = Depends(get_db)):
    return _run_import(service.import_csv, db, body.text, body.source_id)


@router.post('/import/iata')
def import_iata(body: ImportBody, db: Session = Depends(get_db)):
    return _run_import(service.import_iata, db, body.text)


@router.post('/import/bts')
def import_bts(body: ImportBody, db: Session = Depends(get_db)):
    return _run_import(service.import_bts, db, body.text, body.column_map)
