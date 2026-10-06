"""Market Opportunities — cross-country wholesale price comparison +
opportunity scoring (see src/components/marketAnalysis/MarketOpportunitiesPanel.jsx,
which this replaces the "coming soon" placeholder of). Product matching
(curated overrides + translated/exact normalized-name join, generalizing
backend/price_sources/match_table.py's pattern) and unit normalization
happen on the FRONTEND (src/services/marketOpportunities.js), reusing the
same pieces the rest of Market Analysis already built for exactly this —
Colombia's Spanish->English translation dictionary is a frontend-only
concern by design (see productTranslations.js's own header comment), and
buildProductPortfolio/mergeSources already do cross-source joins there, so
duplicating any of that here would be a second copy that could drift from
the real one.

This router does only the two things that genuinely belong on the backend:
a free/keyless FX rate with its own date, every currency converted
independently to a common USD basis (see currency/usd_rates.py — NOT
currency/exchange_rate.py, a separate, paid, differently-cached service
left untouched per the spec), and persisting + scoring the final computed
comparison rows (Step 3/4 of the spec) — the one business rule that defines
this feature's output (the opportunity-rating scale) lives in exactly one
place, here, not duplicated on the frontend."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..currency.usd_rates import get_usd_rate
from ..database import get_db
from .market_opportunity_settings import get_margin_tiers, rating_for

router = APIRouter()


@router.get('/api/market-opportunities/exchange-rate')
def exchange_rate(from_currency: str = Query(alias='from'), db: Session = Depends(get_db)):
    """The given currency's rate against USD — always the common basis now
    (a `to` param used to exist for a since-removed direct pairwise path;
    every comparison converts independently to USD, never source-currency
    straight to target-currency, so there is nothing else to convert to).
    `rate` is how many units of `from_currency` equal 1 USD — divide a
    local price by it to get USD (see currency/usd_rates.py's own
    docstring for why this direction, not its inverse, is what's stored)."""
    result = get_usd_rate(db, from_currency)
    if result is None:
        return {'rate': None, 'date': None, 'from': from_currency.upper(), 'available': False}
    return {'rate': result['rate'], 'date': result['date'], 'from': from_currency.upper(), 'available': True}


# Opportunity rating scale (spec Step 4). Verified against the spec's own
# worked math before implementing, not accepted on faith — confirmed
# correct: diff_pct = (source_price_normalized / target_price_normalized) *
# 100. A LOW diff_pct means the source price is a small fraction of the
# target market's own price — the largest possible margin, correctly at the
# "Very High" opportunity end. As diff_pct climbs toward 100, the two prices
# are converging (a shrinking margin), correctly "Difficult" just under 100.
# Past 100%, the source price actually EXCEEDS the target market's own price
# — there is no margin at all, a fundamentally different situation from a
# thin-but-positive one, not just a more extreme version of "Difficult" — so
# a distinct "Not Viable" tier with its own break exactly at 100 is the
# mathematically correct place to draw it, not an arbitrary addition.
# The scale itself (the ranges below) is now set in Settings ▸ Market Opportunity settings — see
# routers/market_opportunity_settings.py (`get_margin_tiers`, `rating_for`); these were its hardcoded defaults.


class ComparisonIn(BaseModel):
    product_name: str
    target_product_name: str | None = None
    source_country: str
    target_country: str
    hs_code: str | None = None
    source_price_value: float | None = None
    source_price_unit: str | None = None
    source_price_currency: str | None = None
    target_price_value: float | None = None
    target_price_unit: str | None = None
    target_price_currency: str | None = None
    source_price_normalized: float | None = None
    target_price_normalized: float | None = None
    exchange_rate_source_used: float | None = None
    exchange_rate_source_date: str | None = None
    exchange_rate_target_used: float | None = None
    exchange_rate_target_date: str | None = None
    match_tier: str | None = None
    review_reasons: list[str] = []
    conversion_note: str | None = None


class UnmatchedProductIn(BaseModel):
    displayName: str | None = None
    matchName: str | None = None
    category: str | None = None


class ComparisonsIn(BaseModel):
    rows: list[ComparisonIn]
    # {target_country: [source products with no match there]}
    unmatched_by_target: dict[str, list[UnmatchedProductIn]] = {}


def _serialize(row: models.MarketOpportunityComparison) -> dict:
    return {
        'id': row.id,
        'product_name': row.product_name,
        'target_product_name': row.target_product_name,
        'source_country': row.source_country,
        'target_country': row.target_country,
        'hs_code': row.hs_code,
        'source_price_original': {'value': row.source_price_value, 'unit': row.source_price_unit, 'currency': row.source_price_currency},
        'target_price_original': {'value': row.target_price_value, 'unit': row.target_price_unit, 'currency': row.target_price_currency},
        'source_price_normalized': row.source_price_normalized,
        'target_price_normalized': row.target_price_normalized,
        'exchange_rate_source_used': row.exchange_rate_source_used,
        'exchange_rate_source_date': row.exchange_rate_source_date,
        'exchange_rate_target_used': row.exchange_rate_target_used,
        'exchange_rate_target_date': row.exchange_rate_target_date,
        'diff_pct': row.diff_pct,
        'opportunity_rating': row.opportunity_rating,
        'match_tier': row.match_tier,
        'match_confidence': row.match_confidence,
        'review_reasons': json.loads(row.review_reasons_json or '[]'),
        'conversion_note': row.conversion_note,
        'calculated_at': row.calculated_at,
    }


@router.post('/api/market-opportunities/comparisons')
def save_comparisons(payload: ComparisonsIn, db: Session = Depends(get_db)):
    """Computes diff_pct + opportunity_rating server-side from each row's
    already-normalized USD/kg values (the frontend does matching + unit/
    currency normalization; this is the one place the rating scale itself
    lives), then persists every row. Replaces any previously-saved rows for
    the exact (source_country, target_country) pairs in this batch first —
    a Market Opportunities run is a full recompute of its own scope, not an
    incremental patch, same "overwrite on an explicit recompute" convention
    market_size_store.py already uses for SAM/TAM."""
    if not payload.rows:
        raise HTTPException(status_code=400, detail='No rows to save.')

    pairs = {(row.source_country, row.target_country) for row in payload.rows}
    for source_country, target_country in pairs:
        db.query(models.MarketOpportunityComparison).filter_by(
            source_country=source_country, target_country=target_country
        ).delete()

    calculated_at = datetime.now(timezone.utc).isoformat()
    tiers = get_margin_tiers(db)
    saved = []
    for row in payload.rows:
        source_norm = row.source_price_normalized
        target_norm = row.target_price_normalized
        diff_pct = (source_norm / target_norm) * 100 if source_norm is not None and target_norm not in (None, 0) else None
        rating = rating_for(diff_pct, tiers) if diff_pct is not None else None

        reasons = list(row.review_reasons)
        if diff_pct is None:
            reasons.append('Could not normalize both sides to a common USD/kg basis — see the original price, unit and currency.')
        match_confidence = 'confirmed' if not reasons and row.match_tier in ('exact', 'translated_exact') else 'review'

        record = models.MarketOpportunityComparison(
            id=str(uuid.uuid4()),
            product_name=row.product_name,
            target_product_name=row.target_product_name,
            source_country=row.source_country,
            target_country=row.target_country,
            hs_code=row.hs_code,
            source_price_value=row.source_price_value,
            source_price_unit=row.source_price_unit,
            source_price_currency=row.source_price_currency,
            target_price_value=row.target_price_value,
            target_price_unit=row.target_price_unit,
            target_price_currency=row.target_price_currency,
            source_price_normalized=source_norm,
            target_price_normalized=target_norm,
            exchange_rate_source_used=row.exchange_rate_source_used,
            exchange_rate_source_date=row.exchange_rate_source_date,
            exchange_rate_target_used=row.exchange_rate_target_used,
            exchange_rate_target_date=row.exchange_rate_target_date,
            diff_pct=diff_pct,
            opportunity_rating=rating,
            match_tier=row.match_tier,
            match_confidence=match_confidence,
            review_reasons_json=json.dumps(reasons),
            conversion_note=row.conversion_note,
            calculated_at=calculated_at,
        )
        db.add(record)
        saved.append(record)

    # Each pair's unmatched list, replaced along with its rows — only when the
    # caller sent one (an older client that doesn't must not blank it).
    for source_country, target_country in pairs if 'unmatched_by_target' in payload.model_fields_set else ():
        db.query(models.MarketOpportunityUnmatched).filter_by(source_country=source_country, target_country=target_country).delete()
        products = payload.unmatched_by_target.get(target_country, [])
        db.add(
            models.MarketOpportunityUnmatched(
                source_country=source_country,
                target_country=target_country,
                products_json=json.dumps([product.model_dump() for product in products]),
                calculated_at=calculated_at,
            )
        )
    db.commit()
    return {'rows': [_serialize(row) for row in saved], 'calculated_at': calculated_at}


@router.get('/api/market-opportunities/comparisons/pairs')
def list_comparison_pairs(db: Session = Depends(get_db)):
    """Every saved (source_country, target_country) comparison, with its row
    count and when it was last computed, newest first — what Market
    Opportunities lists as its saved comparisons."""
    Comparison = models.MarketOpportunityComparison
    rows = (
        db.query(Comparison.source_country, Comparison.target_country, func.count(Comparison.id), func.max(Comparison.calculated_at))
        .group_by(Comparison.source_country, Comparison.target_country)
        .all()
    )
    pairs = [
        {'source_country': source, 'target_country': target, 'row_count': count, 'calculated_at': calculated_at}
        for source, target, count, calculated_at in rows
    ]
    pairs.sort(key=lambda pair: pair['calculated_at'] or '', reverse=True)
    return {'pairs': pairs}


class PriorityItem(BaseModel):
    source_country: str
    target_country: str
    product_name: str


class PriorityItemsIn(BaseModel):
    items: list[PriorityItem]


def _priority_out(row: models.MarketOpportunityPriority) -> dict:
    return {
        'source_country': row.source_country,
        'target_country': row.target_country,
        'product_name': row.product_name,
        'created_at': row.created_at,
    }


@router.get('/api/market-opportunities/priority')
def list_priority(
    source_country: str = Query(...),
    target_countries: str = Query(default=''),
    db: Session = Depends(get_db),
):
    """The priority list of one source country's comparisons against one or
    more target countries (comma-separated), oldest first."""
    Priority = models.MarketOpportunityPriority
    query = db.query(Priority).filter_by(source_country=source_country)
    targets = [item for item in (target_countries or '').split(',') if item]
    if targets:
        query = query.filter(Priority.target_country.in_(targets))
    return {'items': [_priority_out(row) for row in query.order_by(Priority.created_at)]}


@router.post('/api/market-opportunities/priority')
def add_to_priority(payload: PriorityItemsIn, db: Session = Depends(get_db)):
    """Adds products to their comparisons' priority lists; ones already on
    a list are left as they are."""
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for item in payload.items:
        key = {'source_country': item.source_country, 'target_country': item.target_country, 'product_name': item.product_name}
        if not db.query(models.MarketOpportunityPriority).filter_by(**key).first():
            db.add(models.MarketOpportunityPriority(**key, created_at=now))
            added += 1
    db.commit()
    return {'added': added}


@router.post('/api/market-opportunities/priority/remove')
def remove_from_priority(payload: PriorityItemsIn, db: Session = Depends(get_db)):
    removed = 0
    for item in payload.items:
        removed += (
            db.query(models.MarketOpportunityPriority)
            .filter_by(source_country=item.source_country, target_country=item.target_country, product_name=item.product_name)
            .delete()
        )
    db.commit()
    return {'removed': removed}


@router.get('/api/market-opportunities/comparisons')
def list_comparisons(
    source_country: str = Query(...),
    target_countries: str = Query(default=''),
    db: Session = Depends(get_db),
):
    """Every saved comparison row for one source country against one or
    more target countries (comma-separated — a Target = "By Region" run
    saves several target countries' worth of rows in one POST, all
    retrievable together here)."""
    query = db.query(models.MarketOpportunityComparison).filter_by(source_country=source_country)
    targets = [item for item in (target_countries or '').split(',') if item]
    if targets:
        query = query.filter(models.MarketOpportunityComparison.target_country.in_(targets))
    rows = query.all()
    # Unmatched lists saved with each pair's last run; a pair saved before
    # these were stored has none (null, not an empty list).
    unmatched_query = db.query(models.MarketOpportunityUnmatched).filter_by(source_country=source_country)
    if targets:
        unmatched_query = unmatched_query.filter(models.MarketOpportunityUnmatched.target_country.in_(targets))
    unmatched = {row.target_country: json.loads(row.products_json or '[]') for row in unmatched_query}
    return {'rows': [_serialize(row) for row in rows], 'unmatched_by_target': unmatched}
