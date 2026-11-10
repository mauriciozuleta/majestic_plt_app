"""Is a saved comparison out of date? A comparison is built from the catalogs of both countries, their HS codes, the researched item weights, the translations and the price
levels of the sources. When a run is saved, a fingerprint of those inputs is stored (table market_opportunity_runs); asking later compares it with the data now and names
what changed ("La Mayorista was refreshed on 2026-11-07, after this comparison"). A comparison saved before the table existed is judged by its calculation date against the
catalogs' fetch dates. Nothing here recomputes anything."""

import json

from .. import models
from ..catalog_normalization.catalog import country_of_source


def _catalog_dates(db, countries: list[str]) -> dict[str, str]:
    wanted = {name.lower() for name in countries}
    return {row.source: row.fetched_at for row in db.query(models.PriceComparisonSnapshot).all()
            if row.fetched_at and (country_of_source(db, row.source) or '').lower() in wanted}


def current_inputs(db, countries: list[str]) -> dict:
    from sqlalchemy import func

    assignments = db.query(func.count(), func.max(models.ProductHsAssignment.assigned_at)).one()
    weights = db.query(func.count(), func.max(models.CatalogItemWeight.researched_at)).one()
    from ..portfolio.service import _analysis_types

    return {
        'catalogs': _catalog_dates(db, countries),
        'hs': {'count': assignments[0], 'latest': assignments[1]},
        'weights': {'count': weights[0], 'latest': weights[1]},
        'translations': db.query(func.count(models.ProductTranslationOverride.product_key)).scalar(),
        'levels': _analysis_types(db),
    }


def record_run(db, source_country: str, target_countries: list[str], calculated_at: str, params: dict, result: dict) -> None:
    for target in target_countries:
        inputs = json.dumps(current_inputs(db, [source_country, target]), sort_keys=True)
        row = db.get(models.MarketOpportunityRun, (source_country, target)) or models.MarketOpportunityRun(source_country=source_country, target_country=target)
        row.calculated_at, row.inputs_json, row.params_json = calculated_at, inputs, json.dumps(params)
        row.row_count = sum(1 for item in result['rows'] if item['target_country'] == target)
        row.ai_error, row.weight_error = result['aiMatchErrors'].get(target), result['weightError']
        db.add(row)
    db.commit()


def _label(db, source_key: str) -> str:
    from ..data_history.service import scope_label

    return scope_label(db, f'snapshot:{source_key}')


def pair_status(db, source_country: str, target_country: str, calculated_at: str | None) -> dict:
    """{stale: True | False | None, reasons: [...]} — None when nothing can be said (no calculation date)."""
    run = db.get(models.MarketOpportunityRun, (source_country, target_country))
    now = current_inputs(db, [source_country, target_country])
    reasons: list[str] = []
    if run is None:
        if not calculated_at:
            return {'stale': None, 'reasons': []}
        for source_key, fetched in sorted(now['catalogs'].items()):
            if fetched > calculated_at:
                reasons.append(f'{_label(db, source_key)} was refreshed on {fetched[:10]}, after this comparison ({calculated_at[:10]}).')
        return {'stale': bool(reasons), 'reasons': reasons}
    before = json.loads(run.inputs_json)
    for source_key in sorted(set(now['catalogs']) | set(before['catalogs'])):
        old, new = before['catalogs'].get(source_key), now['catalogs'].get(source_key)
        if old != new:
            reasons.append(f'{_label(db, source_key)} changed' + (f' on {new[:10]}' if new else ' (removed)') + f', after this comparison ({run.calculated_at[:10]}).')
    if before['hs'] != now['hs']:
        reasons.append('HS codes were added or changed after this comparison.')
    if before['weights'] != now['weights']:
        reasons.append('Item weights were researched or edited after this comparison.')
    if before['translations'] != now['translations']:
        reasons.append('Product-name translations changed after this comparison.')
    if before['levels'] != now['levels']:
        reasons.append('A source was switched between wholesale and retail after this comparison.')
    return {'stale': bool(reasons), 'reasons': reasons}
