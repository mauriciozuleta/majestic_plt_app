"""Country Commercial Profile — AI-researched export/import profile for a
commercial country (tariffs, taxes, seasonal bans, protected products,
etc.), built on demand via Claude's web search tool and stored as a .md
file. Building only ever happens on an explicit "Build Profile" click —
no background/scheduled generation. The build itself DOES run as a real
background task once started, though: it's a ~90-second live web-research
call, and tying it to the request/response cycle meant navigating away
(or even just the browser giving up on a long-idle connection) looked like
the job had died, when the backend was actually still working. See
background_jobs.py for how "still building" is tracked across that."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..country_profile.claude_client import build_country_commercial_profile, extract_quick_facts
from ..database import SessionLocal, get_db
from ..knowledge_base.context import business_context, context_prompt_section
from ..trade_gov.commercial_guides import fetch_guide

# Opportunity ratings worth briefing on when there's no priority list.
_GOOD_RATINGS = ('Very High', 'High', 'Challenging')
MAX_PRODUCT_LINES = 40

router = APIRouter()

PROFILES_DIR = Path(__file__).resolve().parent.parent / 'country_profiles'


def _profile_path(country_id: str) -> Path:
    return PROFILES_DIR / f'{country_id}.md'


@router.get('/companies/{company_id}/commercial-countries/profiles')
def list_country_profiles(company_id: str, db: Session = Depends(get_db)):
    """Every country under this company that already has a built profile —
    used by Documentation's link list and by Country Competitiveness
    Analysis's "pick a country to benchmark against" step."""
    countries = db.query(models.CommercialCountry).filter_by(company_id=company_id).all()
    results = []
    for country in countries:
        path = _profile_path(country.id)
        if path.exists():
            results.append(
                {
                    'country_id': country.id,
                    'country_name': country.name,
                    'generated_at': datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return results


@router.get('/companies/{company_id}/commercial-countries/{country_id}/profile')
def get_country_profile(company_id: str, country_id: str, db: Session = Depends(get_db)):
    country = db.query(models.CommercialCountry).filter_by(id=country_id, company_id=company_id).first()
    if not country:
        raise HTTPException(status_code=404, detail='Country not found')

    path = _profile_path(country_id)
    building = is_building(path)
    error = get_error(path)
    if not path.exists():
        return {'exists': False, 'building': building, 'error': error, 'content': None, 'generated_at': None, 'quick_facts': []}

    content = path.read_text(encoding='utf-8')
    generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return {
        'exists': True,
        'building': building,
        'error': error,
        'content': content,
        'generated_at': generated_at,
        'quick_facts': extract_quick_facts(content),
    }


def _our_products(country_name: str) -> dict | None:
    """Our products for this market, from Market Opportunities: the priority
    list for this target country if there is one, otherwise the best-rated
    matched products of its saved comparisons. -> {basis, lines} or None."""
    db = SessionLocal()
    try:
        rows = db.query(models.MarketOpportunityComparison).filter_by(target_country=country_name).all()
        by_name = {}
        for row in rows:
            current = by_name.get((row.source_country, row.product_name))
            if current is None or (row.diff_pct or 1e9) < (current.diff_pct or 1e9):
                by_name[(row.source_country, row.product_name)] = row
        priority = db.query(models.MarketOpportunityPriority).filter_by(target_country=country_name).all()
        if priority:
            picked = [(item.source_country, item.product_name) for item in priority]
            basis = 'our priority list in Market Opportunities'
        else:
            good = [row for row in by_name.values() if row.opportunity_rating in _GOOD_RATINGS]
            good.sort(key=lambda row: (_GOOD_RATINGS.index(row.opportunity_rating), row.diff_pct or 1e9))
            picked = [(row.source_country, row.product_name) for row in good[:MAX_PRODUCT_LINES]]
            basis = 'our best-rated matches in Market Opportunities (no priority list yet)'
        lines = []
        for source, name in picked[:MAX_PRODUCT_LINES]:
            row = by_name.get((source, name))
            detail = [f'from {source}']
            if row and row.hs_code:
                detail.append(f'HS {row.hs_code}')
            if row and row.diff_pct is not None:
                detail.append(f'our price is {row.diff_pct:.0f}% of the local price ({row.opportunity_rating})')
            lines.append(f"{name} — {'; '.join(detail)}")
        return {'basis': basis, 'lines': lines} if lines else None
    finally:
        db.close()


def _run_profile_build(country_id: str, country_name: str, extra_prompt: str = '', document_names: tuple = ()):
    path = _profile_path(country_id)
    try:
        # The official guide is the primary source when the country has one;
        # if trade.gov can't be reached, the build carries on from web research.
        try:
            guide = fetch_guide(country_name)
            guide_note = ''
        except Exception as exc:
            guide, guide_note = None, f' (The Country Commercial Guide could not be read: {exc}.)'
        body = build_country_commercial_profile(country_name, extra_prompt, guide=guide, our_products=_our_products(country_name))
        generated_at = datetime.now(timezone.utc)
        based_on = f' Based on our documents: {", ".join(document_names)}.' if document_names else ''
        if guide:
            published = f", last published {guide['published']}" if guide.get('published') else ''
            source = f" Built from the U.S. Commercial Service's Country Commercial Guide ({len(guide['chapters'])} chapters{published}) and web research."
        else:
            source = f' No Country Commercial Guide for {country_name} — built from web research.{guide_note}'
        header = f'AI-generated — {generated_at.strftime("%B %d, %Y")}.{source}{based_on}\n\n'
        path.write_text(header + body, encoding='utf-8')
    except Exception as exc:
        mark_error(path, str(exc))
    finally:
        clear_building(path)


@router.post('/companies/{company_id}/commercial-countries/{country_id}/profile')
def build_country_profile(company_id: str, country_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    country = db.query(models.CommercialCountry).filter_by(id=country_id, company_id=company_id).first()
    if not country:
        raise HTTPException(status_code=404, detail='Country not found')

    path = _profile_path(country_id)
    if is_building(path):
        return {'status': 'already_building'}

    # The knowledge base's uploaded documents (a business plan, say) are
    # the basis the profile is written for — see knowledge_base/context.py.
    context, document_names = business_context(db, country.name)
    mark_building(path)
    background_tasks.add_task(_run_profile_build, country_id, country.name, context_prompt_section(context), tuple(document_names))
    return {'status': 'started'}
