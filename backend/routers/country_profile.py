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
from ..database import get_db

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


def _run_profile_build(country_id: str, country_name: str):
    path = _profile_path(country_id)
    try:
        body = build_country_commercial_profile(country_name)
        generated_at = datetime.now(timezone.utc)
        header = f'AI-generated — {generated_at.strftime("%B %d, %Y")}.\n\n'
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

    mark_building(path)
    background_tasks.add_task(_run_profile_build, country_id, country.name)
    return {'status': 'started'}
