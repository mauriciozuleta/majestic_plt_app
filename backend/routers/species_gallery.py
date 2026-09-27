"""Variety Gallery API — scientific-name anchoring, the persistent
Species/Variety database, cache-first bootstrap, cross-market matching, and
the review queue (the Variety table's own confidence_status, see
models.Variety's docstring for why this is a new table rather than reusing
ProductTranslationSuggestion).

Structural Tier A/Tier B separation is enforced here, not by convention:
every PUBLIC endpoint below builds its response with schemas.VarietyPublicOut
(no image_tier_a field exists on that model at all — see
backend/routers/species_gallery.py's own test in
backend/tests / the empirical curl check run during development), while the
one internal/admin endpoint that legitimately needs Tier A (for a future
optional CV signal) uses schemas.VarietyAdminOut instead. A public response
is built by explicitly listing VarietyPublicOut's own fields — never by
constructing a dict from the ORM row's __dict__ or passing db_row.characteristics_json
straight through — so there is no code path capable of leaking image_tier_a
into a public response even by accident.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..species_gallery import langsearch_client
from ..species_gallery.bootstrap import bootstrap_variety
from ..species_gallery.discovery import discover_target_varieties
from ..species_gallery.matching import find_best_match
from ..species_gallery.resolver import resolve_scientific_name

router = APIRouter(prefix='/api/species-gallery')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _variety_public_out(row: models.Variety) -> schemas.VarietyPublicOut:
    try:
        characteristics = json.loads(row.characteristics_json) or {}
    except Exception:
        characteristics = {}
    return schemas.VarietyPublicOut(
        id=row.id,
        scientific_name=row.scientific_name,
        variety_name=row.variety_name,
        source_country=row.source_country,
        characteristics=characteristics,
        image_tier_b=row.image_tier_b,
        image_tier_b_license=row.image_tier_b_license,
        image_tier_b_attribution=row.image_tier_b_attribution,
        image_tier_b_source_url=row.image_tier_b_source_url,
        confidence_status=row.confidence_status,
        created_via=row.created_via,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )


def _variety_admin_out(row: models.Variety) -> schemas.VarietyAdminOut:
    public = _variety_public_out(row)
    return schemas.VarietyAdminOut(**public.model_dump(), image_tier_a=row.image_tier_a, bootstrap_note=row.bootstrap_note)


# ---------------------------------------------------------------------------
# Species resolution (spec section 1) — cache-first: a candidate commodity
# term/HS-embedded binomial is deterministic and free to compute, but GBIF
# is only ever called for a scientific name not already cached as a Species
# row (see resolve_scientific_name's own module docstring for why GBIF
# itself can't discover the candidate from a common name in the first
# place).
# ---------------------------------------------------------------------------

class ResolveItem(BaseModel):
    key: str
    name: str
    hs_description: str | None = None


class ResolveRequest(BaseModel):
    items: list[ResolveItem]


@router.post('/resolve')
def resolve_species(request: ResolveRequest, db: Session = Depends(get_db)):
    results = {}
    for item in request.items:
        result = resolve_scientific_name(item.name, item.hs_description)
        if result.status != 'resolved':
            results[item.key] = {'status': 'unresolved', 'reason': result.reason}
            continue

        existing = db.query(models.Species).filter_by(scientific_name=result.scientific_name).first()
        if existing:
            results[item.key] = {
                'status': 'resolved',
                'scientific_name': existing.scientific_name,
                'common_name': existing.common_name,
                'cached': True,
            }
            continue

        species = models.Species(
            scientific_name=result.scientific_name,
            common_name=item.name if result.resolved_from == 'commodity_dictionary_name' else None,
            gbif_key=result.gbif_key,
            gbif_rank=result.gbif_rank,
            kingdom=result.kingdom,
            family=result.family,
            resolved_from=result.resolved_from,
            resolved_term=result.resolved_term,
            created_at=_now(),
        )
        db.add(species)
        db.commit()
        results[item.key] = {
            'status': 'resolved',
            'scientific_name': species.scientific_name,
            'common_name': species.common_name,
            'cached': False,
        }
    return {'results': results}


@router.get('/species', response_model=list[schemas.SpeciesOut])
def list_species(db: Session = Depends(get_db)):
    return db.query(models.Species).order_by(models.Species.scientific_name).all()


# ---------------------------------------------------------------------------
# Public Gallery reads — Tier B only, structurally (VarietyPublicOut has no
# image_tier_a field to leak).
# ---------------------------------------------------------------------------

@router.get('/species/{scientific_name}/varieties', response_model=list[schemas.VarietyPublicOut])
def list_varieties_public(scientific_name: str, db: Session = Depends(get_db)):
    rows = db.query(models.Variety).filter_by(scientific_name=scientific_name).order_by(models.Variety.variety_name).all()
    return [_variety_public_out(row) for row in rows]


# ---------------------------------------------------------------------------
# Internal/admin read — the only endpoint allowed to return image_tier_a.
# ---------------------------------------------------------------------------

@router.get('/admin/varieties/{variety_id}', response_model=schemas.VarietyAdminOut)
def get_variety_admin(variety_id: str, db: Session = Depends(get_db)):
    row = db.query(models.Variety).filter_by(id=variety_id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Variety not found')
    return _variety_admin_out(row)


# ---------------------------------------------------------------------------
# Bootstrap on cache miss (spec section 3) — cache-first: the DB is checked
# BEFORE any bootstrap sub-step runs; a hit never re-triggers LangSearch or
# Commons, ever, for this exact (scientific_name, variety_name,
# source_country) triple.
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    scientific_name: str
    common_name: str | None = None
    variety_name: str
    source_country: str
    category: str = 'produce'


def _persist_bootstrapped_variety(db: Session, scientific_name: str, variety_name: str, source_country: str, bootstrapped: dict) -> models.Variety:
    """Shared by the explicit `/varieties/bootstrap` endpoint and
    `match_variety`'s own discovery step below — both build a
    models.Variety row from a `bootstrap_variety(...)` result the same way,
    always `confidence_status='auto-filled - unverified'`,
    `created_via='bootstrap_search'`, never anything else."""
    row = models.Variety(
        id=str(uuid.uuid4()),
        scientific_name=scientific_name,
        variety_name=variety_name,
        source_country=source_country,
        characteristics_json=bootstrapped['characteristics_json'],
        image_tier_a=bootstrapped['image_tier_a'],
        image_tier_b=bootstrapped['image_tier_b'],
        image_tier_b_license=bootstrapped['image_tier_b_license'],
        image_tier_b_attribution=bootstrapped['image_tier_b_attribution'],
        image_tier_b_source_url=bootstrapped['image_tier_b_source_url'],
        confidence_status='auto-filled - unverified',
        created_via='bootstrap_search',
        bootstrap_note=bootstrapped['bootstrap_note'],
        created_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post('/varieties/bootstrap', response_model=schemas.VarietyAdminOut)
def bootstrap_variety_endpoint(request: BootstrapRequest, db: Session = Depends(get_db)):
    existing = (
        db.query(models.Variety)
        .filter_by(scientific_name=request.scientific_name, variety_name=request.variety_name, source_country=request.source_country)
        .first()
    )
    if existing:
        return _variety_admin_out(existing)  # cache hit — no bootstrap call of any kind

    if not db.query(models.Species).filter_by(scientific_name=request.scientific_name).first():
        raise HTTPException(status_code=400, detail='Unknown species — resolve it via /resolve first')

    bootstrapped = bootstrap_variety(request.scientific_name, request.common_name, request.variety_name, request.source_country, request.category)
    row = _persist_bootstrapped_variety(db, request.scientific_name, request.variety_name, request.source_country, bootstrapped)
    return _variety_admin_out(row)


# ---------------------------------------------------------------------------
# Review queue — every bootstrapped Variety stays 'auto-filled - unverified'
# until a human confirms it here (same queryable-pending / confirm / reject
# shape as price_comparison.py's translation-suggestions, see models.Variety's
# docstring). No AI/paid-API call anywhere in this flow.
# ---------------------------------------------------------------------------

@router.get('/review-queue', response_model=list[schemas.VarietyAdminOut])
def list_review_queue(db: Session = Depends(get_db)):
    rows = db.query(models.Variety).filter_by(confidence_status='auto-filled - unverified').order_by(models.Variety.created_at).all()
    return [_variety_admin_out(row) for row in rows]


@router.post('/review-queue/{variety_id}/confirm', response_model=schemas.VarietyAdminOut)
def confirm_variety(variety_id: str, db: Session = Depends(get_db)):
    row = db.query(models.Variety).filter_by(id=variety_id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Variety not found')
    row.confidence_status = 'confirmed'
    row.confirmed_at = _now()
    db.commit()
    db.refresh(row)
    return _variety_admin_out(row)


@router.delete('/review-queue/{variety_id}')
def reject_variety(variety_id: str, db: Session = Depends(get_db)):
    db.query(models.Variety).filter_by(id=variety_id).delete()
    db.commit()
    return {'status': 'deleted'}


# ---------------------------------------------------------------------------
# Cross-market matching (spec section 4) — deterministic point-scoring,
# never AI/image-similarity. Ensures the source variety exists, then gets
# every known variety of the same species already cached for the target
# country. THIS IS THE STEP THAT USED TO STOP HERE: if nothing was cached
# yet, it just reported "bootstrap one first" and left the workflow fully
# manual — the "Find best match" button only ever searched among whatever a
# human had already bootstrapped one at a time. Now, on a genuine cache
# miss, it discovers real candidate variety names for this species in the
# target country (species_gallery/discovery.py — one LangSearch web search
# + plain keyword extraction, no AI) and bootstraps each one (via the
# EXISTING bootstrap_variety, unchanged) before scoring runs — so a match
# request can find a real answer the first time it's asked, not just the
# n-th time after a human has manually pre-populated the target country.
# Discovery itself is cache-aware: a candidate name already present for
# this (scientific_name, target_country) pair is never re-bootstrapped, and
# the whole step is capped (discovery.MAX_DISCOVERY_CANDIDATES) so one
# match request can't trigger unbounded bootstrap calls.
# ---------------------------------------------------------------------------

class MatchRequest(BaseModel):
    source_variety_id: str
    target_country: str
    category: str = 'produce'


@router.post('/match')
def match_variety(request: MatchRequest, db: Session = Depends(get_db)):
    source_row = db.query(models.Variety).filter_by(id=request.source_variety_id).first()
    if not source_row:
        raise HTTPException(status_code=404, detail='Source variety not found')

    target_rows = (
        db.query(models.Variety)
        .filter_by(scientific_name=source_row.scientific_name, source_country=request.target_country)
        .all()
    )

    discovered_varieties: list[dict] = []
    discovery_note = None
    if not target_rows:
        species_row = db.query(models.Species).filter_by(scientific_name=source_row.scientific_name).first()
        common_name = species_row.common_name if species_row else None
        candidate_names, discovery_note = discover_target_varieties(
            source_row.scientific_name,
            common_name,
            request.target_country,
            existing_variety_names=set(),  # target_rows is already empty here — nothing cached yet for this pair
        )
        for candidate_name in candidate_names:
            # Cache-aware even mid-loop: a prior discovery run (or a human
            # bootstrap in between) may already have created this exact
            # triple — never re-bootstrap it.
            existing = (
                db.query(models.Variety)
                .filter_by(scientific_name=source_row.scientific_name, variety_name=candidate_name, source_country=request.target_country)
                .first()
            )
            if existing:
                target_rows.append(existing)
                continue
            bootstrapped = bootstrap_variety(source_row.scientific_name, common_name, candidate_name, request.target_country, request.category)
            new_row = _persist_bootstrapped_variety(db, source_row.scientific_name, candidate_name, request.target_country, bootstrapped)
            target_rows.append(new_row)
            discovered_varieties.append({'id': new_row.id, 'variety_name': new_row.variety_name})

    if not target_rows:
        return {
            'source_variety': _variety_public_out(source_row).model_dump(),
            'target_country': request.target_country,
            'best_match': None,
            'message': f'No variety of {source_row.scientific_name} is cached for {request.target_country}, and discovery found nothing to bootstrap ({discovery_note}).',
            'discovered_count': 0,
            'discovered_varieties': [],
            'discovery_note': discovery_note,
        }

    result = find_best_match(source_row, target_rows)
    best_row = next((row for row in target_rows if row.id == result.best.variety_id), None) if result.best else None
    return {
        'source_variety': _variety_public_out(source_row).model_dump(),
        'target_country': request.target_country,
        'best_match': _variety_public_out(best_row).model_dump() if best_row else None,
        'score': result.score,
        'max_possible': result.max_possible,
        'field_breakdown': result.field_breakdown,
        'all_candidates': result.all_candidates,
        'discovered_count': len(discovered_varieties),
        'discovered_varieties': discovered_varieties,
        'discovery_note': discovery_note,
    }


# ---------------------------------------------------------------------------
# Cost guardrail (spec's own requirement): counts distinct
# (scientific_name, variety_name, country) combinations that would need a
# genuine bootstrap (LangSearch/Commons calls) WITHOUT calling either —
# species resolution itself may call GBIF (free, keyless), but never
# LangSearch/Commons. Report this number before running any real bulk
# bootstrap.
# ---------------------------------------------------------------------------

class CostGuardrailItem(BaseModel):
    name: str
    hs_description: str | None = None
    countries: list[str]


class CostGuardrailRequest(BaseModel):
    items: list[CostGuardrailItem]


@router.post('/cost-guardrail')
def cost_guardrail_count(request: CostGuardrailRequest, db: Session = Depends(get_db)):
    existing_pairs = {(row.scientific_name, row.variety_name, row.source_country) for row in db.query(models.Variety).all()}

    would_bootstrap = []
    unresolved_count = 0
    resolved_species = set()
    for item in request.items:
        result = resolve_scientific_name(item.name, item.hs_description)
        if result.status != 'resolved':
            unresolved_count += 1
            continue
        resolved_species.add(result.scientific_name)
        for country in item.countries:
            key = (result.scientific_name, item.name, country)
            if key not in existing_pairs:
                would_bootstrap.append({'scientific_name': result.scientific_name, 'variety_name': item.name, 'country': country})

    return {
        'total_items': len(request.items),
        'unresolved_count': unresolved_count,
        'distinct_species_resolved': len(resolved_species),
        'would_bootstrap_count': len(would_bootstrap),
        'would_bootstrap_sample': would_bootstrap[:25],
    }


@router.get('/config-status')
def config_status():
    """Whether each optional external dependency is configured — shown in
    the Gallery UI so 'LangSearch not configured' is a visible, honest
    state rather than a silent no-op."""
    return {'langsearch_configured': langsearch_client.is_configured()}
