"""Query resolution with provenance.

Order tried for a place: airport -> country -> region -> global (observed data only), then an optional ESTIMATE (regional/global scheduled benchmark + a country adjustment
you supplied). The answer always says which level was used (`geo_level_used`) next to the one asked for. Only enabled sources count. For `non_scheduled` nothing wholesale is
ever substituted: if no retail-type data exists the answer is status `no_retail_data` (the scheduled answer, if any, is attached separately under `scheduled_reference`).
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import models as m

LEVELS = ('airport', 'country', 'region', 'global')
PERIOD_RANK = {'day': 0, 'week': 1, 'month': 2}


def _enabled_ids(db: Session) -> list[str]:
    return [s.id for s in db.query(m.FuelSource).filter(m.FuelSource.enabled.is_(True)).all()]


def _latest(db: Session, source_ids: list[str], level: str, operator_class: str, place: dict, date_from: date | None, date_to: date | None):
    q = db.query(m.FuelObservation).filter(
        m.FuelObservation.series_kind == 'price', m.FuelObservation.geo_level == level, m.FuelObservation.operator_class == operator_class,
        m.FuelObservation.source_id.in_(source_ids), m.FuelObservation.quality != 'estimated')
    if level == 'airport':
        q = q.filter(m.FuelObservation.airport_iata == place['airport'])
    elif level == 'country':
        q = q.filter(m.FuelObservation.country_iso2 == place['country'])
    elif level == 'region':
        q = q.filter(m.FuelObservation.region_code == place['region'])
    if date_from:
        q = q.filter(m.FuelObservation.obs_date >= date_from)
    if date_to:
        q = q.filter(m.FuelObservation.obs_date <= date_to)
    rows = q.order_by(m.FuelObservation.obs_date.desc()).limit(40).all()
    if not rows:
        return None
    newest = rows[0].obs_date
    # several series can hold the same day (daily vs monthly): prefer the finest period, then the highest-confidence quality
    same = [r for r in rows if r.obs_date == newest]
    return sorted(same, key=lambda r: PERIOD_RANK.get(r.period_type, 9))[0]


def _change(db: Session, row: m.FuelObservation, days: int):
    target = row.obs_date - timedelta(days=days)
    earlier = (db.query(m.FuelObservation).filter(m.FuelObservation.series_id == row.series_id, m.FuelObservation.operator_class == row.operator_class,
                                                  m.FuelObservation.obs_date <= target).order_by(m.FuelObservation.obs_date.desc()).first())
    if not earlier or (target - earlier.obs_date).days > max(10, days // 3):
        return None
    return {'abs': round(row.value_usd_per_gal - earlier.value_usd_per_gal, 4), 'pct': round((row.value_usd_per_gal / earlier.value_usd_per_gal - 1) * 100, 2),
            'from': earlier.obs_date.isoformat()}


def _answer(db: Session, row: m.FuelObservation, requested: str, today: date) -> dict:
    source = db.get(m.FuelSource, row.source_id)
    return {
        'status': 'ok', 'value': round(row.value_usd_per_gal, 4), 'unit': 'USD/US gal', 'as_of': row.obs_date.isoformat(), 'geo_level_used': row.geo_level,
        'geo_level_requested': requested, 'place_used': row.airport_iata or row.country_iso2 or row.region_code or 'GLOBAL', 'operator_class': row.operator_class,
        'price_basis': row.price_basis, 'source': row.source_id, 'source_name': source.name if source else row.source_id, 'quality': row.quality, 'confidence': row.confidence,
        'freshness_days': (today - row.obs_date).days, 'series_id': row.series_id, 'period_type': row.period_type,
        'original': {'value': row.value_original, 'unit': row.unit_original, 'currency': row.currency_original},
        'changes': {'1w': _change(db, row, 7), '1m': _change(db, row, 30), '1y': _change(db, row, 365)}}


def _resolve_class(db: Session, ids: list[str], place: dict, requested: str, cls: str, date_from, date_to, today: date) -> dict:
    chain = [lvl for lvl in LEVELS if lvl != 'airport' or place['airport']]
    if not place['country']:
        chain = [lvl for lvl in chain if lvl not in ('country',)]
    if not place['region']:
        chain = [lvl for lvl in chain if lvl != 'region']
    for level in chain:
        row = _latest(db, ids, level, cls, place, date_from, date_to)
        if row:
            out = _answer(db, row, requested, today)
            out['note'] = None if level == requested else f'No observed {cls} data at {requested} level; showing the {level} series.'
            return out
    estimate = _estimate(db, ids, place, requested, cls, date_from, date_to, today)
    if estimate:
        return estimate
    return {'status': 'no_retail_data' if cls == 'non_scheduled' else 'no_data', 'operator_class': cls, 'geo_level_requested': requested, 'value': None,
            'message': ('No observed non-scheduled (retail) data for this place. A wholesale price is not shown in its place.' if cls == 'non_scheduled'
                        else 'No observed scheduled-carrier data for this place or its region/global fallback. Import data or enable a source.')}


def _estimate(db: Session, ids: list[str], place: dict, requested: str, cls: str, date_from, date_to, today: date):
    if not place['country']:
        return None
    adj = db.query(m.FuelAdjustment).filter_by(country_iso2=place['country'], operator_class=cls).first()
    if not adj:
        return None
    for level in ('region', 'global'):
        if level == 'region' and not place['region']:
            continue
        base = _latest(db, ids, level, 'scheduled', place, date_from, date_to)
        if base:
            value = base.value_usd_per_gal + adj.add_usd_per_gal
            return {
                'status': 'ok', 'value': round(value, 4), 'unit': 'USD/US gal', 'as_of': base.obs_date.isoformat(), 'geo_level_used': level, 'geo_level_requested': requested,
                'place_used': base.region_code or 'GLOBAL', 'operator_class': cls, 'price_basis': 'estimate', 'source': base.source_id, 'source_name': base.source_id,
                'quality': 'estimated', 'confidence': 0.3, 'freshness_days': (today - base.obs_date).days, 'series_id': None, 'period_type': base.period_type,
                'original': None, 'changes': {},
                'formula': f'{level} scheduled benchmark {base.value_usd_per_gal:.4f} + {place["country"]} adjustment {adj.add_usd_per_gal:+.4f} ({adj.note or "no note"}) = {value:.4f}',
                'note': 'ESTIMATE — not an observed price.'}
    return None


def get_price(db: Session, *, country: str | None = None, airport: str | None = None, operator_class: str = 'scheduled', date_from: date | None = None,
              date_to: date | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    airport = airport.upper() if airport else None
    country = country.upper() if country else None
    region = None
    if airport:
        ap = db.get(m.FuelAirport, airport)
        if not ap:
            return {'status': 'unknown_place', 'message': f'Unknown IATA code {airport}.'}
        country = country or ap.country_iso2
    if country:
        c = db.get(m.FuelCountry, country)
        region = c.region_code if c else None
    place = {'airport': airport, 'country': country, 'region': region}
    requested = 'airport' if airport else 'country' if country else 'global'
    ids = _enabled_ids(db)
    classes = ['scheduled', 'non_scheduled'] if operator_class == 'both' else [operator_class]
    results = {cls: _resolve_class(db, ids, place, requested, cls, date_from, date_to, today) for cls in classes}
    if 'non_scheduled' in results and results['non_scheduled']['status'] != 'ok' and 'scheduled' not in results:
        ref = _resolve_class(db, ids, place, requested, 'scheduled', date_from, date_to, today)
        if ref['status'] == 'ok':
            results['non_scheduled']['scheduled_reference'] = ref
    return {'place': {'airport': airport, 'country': country, 'region': region}, 'results': results}
