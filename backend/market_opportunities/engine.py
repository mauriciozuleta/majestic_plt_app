"""The Market Opportunities engine on the server (moved from src/services/marketOpportunities.js): compute the cross-country price comparison of one source country against
target countries, save it, and say whether a saved one is out of date. A port, line for line, of `computeMarketOpportunity`, `getOrComputeComparison` and
`fetchCountryProductPrices`; its output on the frozen inputs equals what the JavaScript produced (backend/tests/test_market_opportunities_parity.py).

What it costs, and how to run it unattended:
  * `allow_ai`       the AI judge (Claude, cached) of tier 3. Off: the engine falls back to shared-HS-code pairing, free.
  * `allow_research` web research of the weight of one item for per-unit prices that only the matched pairs need (Claude with web search). Off: those prices stay unconverted.
  * `save=False`     computes and returns, saves nothing (a simulation).
With both flags off a run is free, deterministic and finishes in seconds."""

import json
import time
from datetime import datetime, timezone

from .. import models
from ..catalog_normalization.catalog import hs_chapters_from_db, researchable
from ..catalog_normalization.service import normalize_price
from ..catalog_normalization.store import DbStore, product_key
from ..catalog_normalization.units import parse_unit
from ..portfolio.merge import per_kg
from . import collect, match, rows

POLL_SECONDS = 4
MAX_WAIT_SECONDS = 20 * 60


# ---------------------------------------------------------------- exchange rates

def fetch_rates(db, currencies) -> dict:
    """{code: {rate, date, from, available}} — every currency converts independently to USD (rate = units of that currency per 1 USD; DIVIDE a local price by it). A currency
    with no rate anywhere is {available: False}, never an error: the affected side is shown as unresolved."""
    from ..currency.usd_rates import get_usd_rate

    rates = {}
    for code in sorted(currencies):
        try:
            found = get_usd_rate(db, code)
        except Exception:  # noqa: BLE001 — no rate service reachable: the comparison still shows what it can
            found = None
        rates[code] = {'rate': found['rate'], 'date': found['date'], 'from': code.upper(), 'available': True} if found else {'rate': None, 'date': None, 'from': code.upper(), 'available': False}
    return rates


# ---------------------------------------------------------------- item weights

def convert_row(db, name: str, unit: str, price) -> dict:
    """One catalog row converted with what is in the weight store now (the same call as GET /api/catalog-normalization/convert)."""
    parsed = parse_unit(unit or '', name)
    return normalize_price(name, unit or '', price, DbStore(db), parsed=parsed, researchable=researchable(name, unit or '', hs_chapters_from_db(db))).to_dict()


def research_weights(db, names: list[str], limit: int) -> str | None:
    """Researches the weight of one item for these products (the names the module reads), waiting for the job like the browser did. -> the reason it failed, or None."""
    from ..background_jobs import clear_building, get_error, is_building, mark_building
    from ..routers import catalog_normalization as cn

    if is_building(cn.JOB_MARKER):  # a run is already going: wait for it
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while is_building(cn.JOB_MARKER) and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
        return get_error(cn.JOB_MARKER)
    wanted = {product_key(name) for name in names}
    chosen = [entry for entry in cn._needs(db) if product_key(entry['product']) in wanted][:max(0, limit)]
    if not chosen:
        return None
    mark_building(cn.JOB_MARKER)
    try:
        cn._run_research([(entry['product'], entry['count_unit']) for entry in chosen])  # clears the marker itself and records a failure there
    finally:
        clear_building(cn.JOB_MARKER)
    return get_error(cn.JOB_MARKER)


def resolve_count_weight_conversions(db, pairs: list[dict], allow_research: bool, research_fn=None, convert_fn=None) -> str | None:
    """A matched product whose price is per unit ("each", a bunch, a counted bag) cannot be compared with the other side's $/kg until the weight of ONE item is known. That
    is researched only for the MATCHED pairs that need it (one side unconvertible while the other is already a $/kg price — never every count-based product, which would be
    wasted spend), then those rows are converted again with what was found. -> an error message, or None."""
    wanted: dict[str, list[dict]] = {}
    for pair in pairs:
        for index, product in enumerate((pair['sp'], pair['tp'])):
            counterpart = pair['tp'] if index == 0 else pair['sp']
            if product.get('perKgLocal') is not None or counterpart.get('perKgLocal') is None:
                continue
            norm = product.get('norm') or {}
            if norm.get('method') != 'needs_research' or not norm.get('read_name'):
                continue
            wanted.setdefault(norm['read_name'], []).append(product)
    if not wanted or not allow_research:
        return None
    error = (research_fn or (lambda names, limit: research_weights(db, names, limit)))(list(wanted), len(wanted))
    convert = convert_fn or (lambda name, unit, price: convert_row(db, name, unit, price))
    for product in [item for items in wanted.values() for item in items]:
        try:
            converted = convert(product['norm']['read_name'], product['norm'].get('read_unit'), product.get('priceValue'))
        except Exception:  # noqa: BLE001 — the row stays unconverted, with its own explanation
            continue
        if per_kg(converted) is None:
            continue
        product['norm'] = {**product['norm'], **converted}
        product['perKgLocal'] = converted['price_per_kg']
        product['unitComment'] = converted.get('note')
        if converted.get('method') in ('researched_item_weight', 'reference_item_weight', 'retail_unit_weight'):
            product['conversionMethod'], product['conversionNote'], product['conversionConfidence'] = converted['method'], converted.get('note'), converted.get('confidence')
    return error


# ---------------------------------------------------------------- the comparison

def ai_match_function(db):
    from ..routers.product_matches import MatchRequest, request_product_matches

    return lambda target_country, groups: request_product_matches(MatchRequest(target_country=target_country, groups=groups), db)


def compute(db, source_country: str, target_countries: list[str], *, allow_ai: bool = True, allow_research: bool = True, rates: dict | None = None,
            match_fn=None, research_fn=None, convert_fn=None) -> dict:
    """-> {rows, unmatchedByTarget: {target: [{displayName, matchName, category}]}, sourceProductCount, aiMatchErrors: {target: reason}, aiSkipped: [targets], weightError}.
    Computes only; saving is `save`. Each target runs in the order given (the browser ran them side by side, so the order of rows across targets was left to chance)."""
    all_countries = [source_country, *[name for name in target_countries if name != source_country]]
    products_by_country = {name: collect.country_products(db, name) for name in all_countries}
    collect.attach_context(db, products_by_country)
    source_products = products_by_country.get(source_country, [])

    currencies = {p['priceCurrency'] for products in products_by_country.values() for p in products if p.get('priceCurrency')}
    rate_table = rates if rates is not None else fetch_rates(db, currencies)

    matched_pairs: list[dict] = []
    unmatched: dict[str, list[dict]] = {}
    ai_errors: dict[str, str] = {}
    ai_skipped: list[str] = []
    for target in target_countries:
        target_products = products_by_country.get(target, [])
        pairs, paired = match.name_pairs(source_country, target, source_products, target_products)
        # a failed AI call never fails the whole comparison: that target falls back to shared-HS-code pairing and the reason is returned
        if allow_ai:
            try:
                answer = match.resolve_ai_matches(source_country, target, source_products, paired, target_products, match_fn or ai_match_function(db))
                if answer['error']:
                    ai_errors[target] = answer['error']
                extra = [*answer['pairs'], *match.hs_code_fallback_pairs(answer['unjudged'], paired, target_products, target)]
            except Exception as error:  # noqa: BLE001
                ai_errors[target] = str(error)
                extra = match.hs_code_fallback_pairs(source_products, paired, target_products, target)
        else:
            ai_skipped.append(target)
            extra = match.hs_code_fallback_pairs(source_products, paired, target_products, target)
        all_pairs = [*pairs, *extra]
        matched_ids = {id(pair['sp']) for pair in all_pairs}
        matched_pairs.extend(all_pairs)
        unmatched[target] = [sp for sp in source_products if id(sp) not in matched_ids]

    weight_error = resolve_count_weight_conversions(db, matched_pairs, allow_research, research_fn, convert_fn)
    pair_rows = [rows.build_comparison_row(p['sp'], p['tp'], p['matchTier'], source_country, p['targetCountry'], rate_table, p.get('aiNote')) for p in matched_pairs]
    return {
        'rows': rows.one_row_per_source_product(matched_pairs, pair_rows),
        'unmatchedByTarget': {target: [{'displayName': p['displayName'], 'matchName': p['matchName'], 'category': p.get('category')} for p in products] for target, products in unmatched.items()},
        'sourceProductCount': len(source_products),
        'aiMatchErrors': ai_errors,
        'aiSkipped': ai_skipped,
        'weightError': weight_error,
    }


def save(db, source_country: str, target_countries: list[str], result: dict, params: dict) -> dict:
    """Persists a computed comparison with the existing save logic (diff %, rating, confidence) and records what it was built from. Nothing is saved when no rows matched
    (the previous comparison, if any, stays). -> {calculated_at, rows: [..]} or {rows: []}."""
    from ..routers.market_opportunities import ComparisonsIn, save_comparisons
    from . import staleness

    if not result['rows']:
        return {'rows': [], 'calculated_at': datetime.now(timezone.utc).isoformat()}
    payload = [{key: value for key, value in row.items() if key != '_target_display_name'} | {'target_product_name': row.get('_target_display_name')} for row in result['rows']]
    saved = save_comparisons(ComparisonsIn(rows=payload, unmatched_by_target=result['unmatchedByTarget']), db)
    staleness.record_run(db, source_country, target_countries, saved['calculated_at'], params, result)
    return saved


def saved_targets(db, source_country: str, target_countries: list[str]) -> set[str]:
    return {name for (name,) in db.query(models.MarketOpportunityComparison.target_country).filter(
        models.MarketOpportunityComparison.source_country == source_country, models.MarketOpportunityComparison.target_country.in_(target_countries)).distinct()}


def get_or_compute(db, source_country: str, target_countries: list[str], *, force: bool = False, allow_ai: bool = True, allow_research: bool = True, **hooks) -> dict:
    """The saved comparison when every target already has one (no recompute, no AI calls), otherwise — or with `force` — a fresh run, saved before it is returned.
    -> {origin: 'saved' | 'computed', row_count, calculated_at, unmatched_by_target, ai_errors, ai_skipped, weight_error, source_product_count}."""
    if not force and saved_targets(db, source_country, target_countries) >= set(target_countries):
        rows_ = db.query(models.MarketOpportunityComparison).filter(models.MarketOpportunityComparison.source_country == source_country,
                                                                    models.MarketOpportunityComparison.target_country.in_(target_countries)).all()
        unmatched = {row.target_country: json.loads(row.products_json or '[]') for row in db.query(models.MarketOpportunityUnmatched).filter(
            models.MarketOpportunityUnmatched.source_country == source_country, models.MarketOpportunityUnmatched.target_country.in_(target_countries))}
        return {'origin': 'saved', 'row_count': len(rows_), 'calculated_at': min(row.calculated_at for row in rows_), 'unmatched_by_target': unmatched,
                'ai_errors': {}, 'ai_skipped': [], 'weight_error': None, 'source_product_count': None}
    result = compute(db, source_country, target_countries, allow_ai=allow_ai, allow_research=allow_research, **hooks)
    saved = save(db, source_country, target_countries, result, {'allow_ai': allow_ai, 'allow_research': allow_research})
    return {'origin': 'computed', 'row_count': len(saved['rows']), 'calculated_at': saved['calculated_at'], 'unmatched_by_target': result['unmatchedByTarget'],
            'ai_errors': result['aiMatchErrors'], 'ai_skipped': result['aiSkipped'], 'weight_error': result['weightError'], 'source_product_count': result['sourceProductCount']}


# ---------------------------------------------------------------- a country's prices in USD/kg

def country_prices(db, country: str, rates: dict | None = None) -> list[dict]:
    """Every product of a country's portfolio with its price per kg in USD (None where the unit or currency could not be converted) and its HS code:
    [{name, category, hsCode, priceUsdPerKg, original: {value, unit, currency}, source}]. Matched in another market or not — the same collectors the comparison uses, so a
    price here is the price the comparison would use. What the tax-multiplier and shipment-cost screens ask for."""
    products = collect.country_products(db, country)
    rate_table = rates if rates is not None else fetch_rates(db, {p['priceCurrency'] for p in products if p.get('priceCurrency')})
    by_name: dict[str, dict] = {}
    for p in products:
        key = p['displayName'].strip().lower()
        rate = rate_table.get(p['priceCurrency']) if p.get('priceCurrency') else None
        usd_value = p['perKgLocal'] / rate['rate'] if p.get('perKgLocal') is not None and (rate or {}).get('available') else None
        entry = {'name': p['displayName'].strip(), 'category': p.get('category') or None, 'hsCode': (p.get('hs') or {}).get('hs6') or None, 'priceUsdPerKg': usd_value,
                 'original': {'value': p['priceValue'], 'unit': p.get('priceUnit'), 'currency': p.get('priceCurrency')} if p.get('priceValue') is not None else None,
                 'source': p['sourceLabel']}
        if key not in by_name or (by_name[key]['priceUsdPerKg'] is None and usd_value is not None):
            by_name[key] = entry
    return sorted(by_name.values(), key=lambda entry: entry['name'].casefold())
