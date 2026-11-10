"""Market Access Brief (formerly the Competitiveness Analysis; the route, the files and the listings keep their old names) — assesses whether a source country's
products can ENTER a target country and what restricts them (bans, permits, seasonal rules, agreements), per HS heading, from the target's already-built Country
Commercial Profile. It does not judge price competitiveness: prices, taxes and freight are computed numerically by Market Opportunities, the tax calculators and the
Shipment Builder. The portfolio is built on the server from the stored catalogs (country_profile/access_pack.py), so a person, the Assistant or an agent can start it.
Requires the target country to have a profile already (see country_profile.py)."""

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..country_profile import access_pack
from ..country_profile.claude_client import build_competitiveness_analysis, extract_quick_facts
from ..data_history import service as data_history_service
from ..database import get_db
from ..knowledge_base.context import business_context, context_prompt_section
from .country_profile import PROFILES_DIR

router = APIRouter()

ANALYSES_DIR = Path(__file__).resolve().parent.parent / 'competitiveness_analyses'


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def _analysis_path(target_country_id: str, source_country_name: str) -> Path:
    return ANALYSES_DIR / f'{target_country_id}__{_slug(source_country_name)}.md'


TITLE_LINE = re.compile(r'^# (.+?) → (.+?) — ', re.MULTILINE)


@router.get('/companies/{company_id}/commercial-countries/competitiveness-analyses')
def list_competitiveness_analyses(company_id: str, db: Session = Depends(get_db)):
    """Every saved (source → target) analysis for this company's countries
    — used by Documentation's link list. The source name is recovered from
    the document's own title line rather than the slugged filename, since
    slugging is lossy (casing/spacing) but the title line isn't."""
    countries_by_id = {c.id: c for c in db.query(models.CommercialCountry).filter_by(company_id=company_id).all()}
    if not countries_by_id or not ANALYSES_DIR.exists():
        return []

    results = []
    for path in ANALYSES_DIR.glob('*.md'):
        target_id = path.stem.split('__', 1)[0]
        target = countries_by_id.get(target_id)
        if not target:
            continue
        content = path.read_text(encoding='utf-8')
        title_match = TITLE_LINE.search(content)
        source_name = title_match.group(1) if title_match else 'Unknown source'
        results.append(
            {
                'target_country_id': target.id,
                'target_country_name': target.name,
                'source_country_name': source_name,
                'generated_at': datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return results


@router.get('/companies/{company_id}/commercial-countries/{target_country_id}/competitiveness')
def get_competitiveness_analysis(
    company_id: str, target_country_id: str, source_country_name: str, db: Session = Depends(get_db)
):
    target = db.query(models.CommercialCountry).filter_by(id=target_country_id, company_id=company_id).first()
    if not target:
        raise HTTPException(status_code=404, detail='Target country not found')

    path = _analysis_path(target_country_id, source_country_name)
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


def _run_competitiveness_build(
    path: Path, source_country_name: str, access_pack: str, target_name: str, target_profile: str,
    extra_prompt: str = '', document_names: tuple = (), web_search: bool = False,
):
    try:
        body = build_competitiveness_analysis(source_country_name, access_pack, target_name, target_profile, extra_prompt, web_search)
        generated_at = datetime.now(timezone.utc)
        based_on = f' Based on our documents: {", ".join(document_names)}.' if document_names else ''
        header = f'AI-generated — {generated_at.strftime("%B %d, %Y")}.{based_on}\n\n'
        path.write_text(header + body, encoding='utf-8')
        data_history_service.record_file(path, 'market access brief built')
    except Exception as exc:
        mark_error(path, str(exc))
    finally:
        clear_building(path)


@router.post('/companies/{company_id}/commercial-countries/{target_country_id}/competitiveness')
def build_competitiveness(
    company_id: str,
    target_country_id: str,
    background_tasks: BackgroundTasks,
    source_country_name: str = Body(...),
    category_summary: list[dict] | None = Body(None),  # no longer used: the server builds the portfolio itself; accepted so older callers keep working
    web_search: bool = Body(False),
    db: Session = Depends(get_db),
):
    target = db.query(models.CommercialCountry).filter_by(id=target_country_id, company_id=company_id).first()
    if not target:
        raise HTTPException(status_code=404, detail='Target country not found')

    profile_path = PROFILES_DIR / f'{target_country_id}.md'
    if not profile_path.exists():
        raise HTTPException(status_code=400, detail=f'{target.name} needs a Country Commercial Profile before it can be used as a benchmark')

    pack = access_pack.portfolio_by_heading(db, source_country_name)
    if not pack['product_count']:
        raise HTTPException(status_code=400, detail=f'No product data is stored for {source_country_name} yet — load or update its Product Analysis source first.')
    access_text = access_pack.render(pack, access_pack.comparison_facts(db, source_country_name, target.name))

    path = _analysis_path(target_country_id, source_country_name)
    if is_building(path):
        return {'status': 'already_building'}

    target_profile = profile_path.read_text(encoding='utf-8')
    mark_building(path)
    context, document_names = business_context(db, f'{target.name} {source_country_name}')
    background_tasks.add_task(
        _run_competitiveness_build, path, source_country_name, access_text, target.name, target_profile,
        context_prompt_section(context), tuple(document_names), web_search,
    )
    return {'status': 'started'}
