"""Risk Analysis & Management — per-company risk register: categories (6
predefined, lazily seeded, or custom ones the user adds) containing risks,
each rated on Exposure (Probability x Impact) and covered by management
mechanisms rated on Capacity x Cost. See risk_scoring.py for the scale and
formulas, and risk_analysis/claude_client.py for the investor-facing
"Generate Plan" narrative writer.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..background_jobs import clear_building, get_error, is_building, mark_building, mark_error
from ..database import get_db
from .. import models
from ..risk_analysis.claude_client import generate_risk_plan
from ..risk_scoring import exposure_score, is_well_managed, management_tier, mechanism_score, mitigation_score, net_score

router = APIRouter()

PLANS_DIR = Path(__file__).resolve().parent.parent / 'risk_plans'

DEFAULT_CATEGORIES = [
    ('Market', '#35D399'),
    ('Competition', '#38BDF8'),
    ('Operational / Technological', '#F59E0B'),
    ('Financial', '#A78BFA'),
    ('Team / Administrative', '#2DD4BF'),
    ('Regulatory / Political', '#F87171'),
]
CUSTOM_PALETTE = ['#FB7185', '#C084FC', '#FACC15', '#34D399', '#60A5FA', '#F97316']

LEVELS = {'VL', 'L', 'M', 'H', 'VH'}


class CategoryCreate(BaseModel):
    name: str


class CategoryUpdate(BaseModel):
    name: str


class RiskCreate(BaseModel):
    name: str
    description: str | None = None


class RiskUpdate(BaseModel):
    name: str
    description: str | None = None
    probability: str
    impact: str


class MechanismCreate(BaseModel):
    name: str
    description: str | None = None


class MechanismUpdate(BaseModel):
    name: str
    description: str | None = None
    capacity: str
    cost: str


def _validate_level(value: str, field_name: str):
    if value not in LEVELS:
        raise HTTPException(status_code=400, detail=f'{field_name} must be one of {sorted(LEVELS)}')


def _ensure_default_categories(db: Session, company_id: str):
    existing_count = db.query(models.RiskCategory).filter_by(company_id=company_id).count()
    if existing_count > 0:
        return
    for index, (name, color) in enumerate(DEFAULT_CATEGORIES):
        db.add(
            models.RiskCategory(
                id=str(uuid.uuid4()),
                company_id=company_id,
                name=name,
                color=color,
                sort_order=index,
                is_custom=False,
            )
        )
    db.commit()


def _next_custom_color(db: Session, company_id: str) -> str:
    count = db.query(models.RiskCategory).filter_by(company_id=company_id).count()
    return CUSTOM_PALETTE[count % len(CUSTOM_PALETTE)]


def _mechanism_out(mechanism: models.RiskMechanism) -> dict:
    return {
        'id': mechanism.id,
        'risk_id': mechanism.risk_id,
        'name': mechanism.name,
        'description': mechanism.description,
        'capacity': mechanism.capacity,
        'cost': mechanism.cost,
        'score': mechanism_score(mechanism),
    }


def _risk_out(risk: models.Risk, mechanisms: list[models.RiskMechanism]) -> dict:
    net = net_score(risk, mechanisms)
    return {
        'id': risk.id,
        'category_id': risk.category_id,
        'name': risk.name,
        'description': risk.description,
        'probability': risk.probability,
        'impact': risk.impact,
        'exposure_score': exposure_score(risk),
        'mitigation_score': mitigation_score(mechanisms),
        'net_score': net,
        'management_tier': management_tier(net, bool(mechanisms)),
        'mechanisms': [_mechanism_out(m) for m in mechanisms],
    }


@router.get('/companies/{company_id}/risk-analysis')
def get_risk_analysis(company_id: str, db: Session = Depends(get_db)):
    _ensure_default_categories(db, company_id)
    categories = (
        db.query(models.RiskCategory)
        .filter_by(company_id=company_id)
        .order_by(models.RiskCategory.sort_order, models.RiskCategory.id)
        .all()
    )
    result = []
    for category in categories:
        risks = db.query(models.Risk).filter_by(category_id=category.id).order_by(models.Risk.sort_order, models.Risk.id).all()
        risk_outs = []
        for risk in risks:
            mechanisms = (
                db.query(models.RiskMechanism)
                .filter_by(risk_id=risk.id)
                .order_by(models.RiskMechanism.sort_order, models.RiskMechanism.id)
                .all()
            )
            risk_outs.append(_risk_out(risk, mechanisms))
        result.append(
            {
                'id': category.id,
                'name': category.name,
                'color': category.color,
                'is_custom': category.is_custom,
                'risks': risk_outs,
            }
        )
    return {'categories': result}


@router.post('/companies/{company_id}/risk-categories')
def create_category(company_id: str, payload: CategoryCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Category name is required')
    count = db.query(models.RiskCategory).filter_by(company_id=company_id).count()
    category = models.RiskCategory(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name=name,
        color=_next_custom_color(db, company_id),
        sort_order=count,
        is_custom=True,
    )
    db.add(category)
    db.commit()
    return {'id': category.id, 'name': category.name, 'color': category.color, 'is_custom': True, 'risks': []}


@router.put('/risk-categories/{category_id}')
def update_category(category_id: str, payload: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.query(models.RiskCategory).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Category not found')
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Category name is required')
    category.name = name
    db.commit()
    return {'id': category.id, 'name': category.name}


@router.delete('/risk-categories/{category_id}')
def delete_category(category_id: str, db: Session = Depends(get_db)):
    category = db.query(models.RiskCategory).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Category not found')
    risk_ids = [row.id for row in db.query(models.Risk).filter_by(category_id=category_id).all()]
    if risk_ids:
        db.query(models.RiskMechanism).filter(models.RiskMechanism.risk_id.in_(risk_ids)).delete(synchronize_session=False)
        db.query(models.Risk).filter(models.Risk.id.in_(risk_ids)).delete(synchronize_session=False)
    db.delete(category)
    db.commit()
    return {'ok': True}


@router.post('/risk-categories/{category_id}/risks')
def create_risk(category_id: str, payload: RiskCreate, db: Session = Depends(get_db)):
    category = db.query(models.RiskCategory).filter_by(id=category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Category not found')
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Risk name is required')
    count = db.query(models.Risk).filter_by(category_id=category_id).count()
    risk = models.Risk(
        id=str(uuid.uuid4()),
        category_id=category_id,
        company_id=category.company_id,
        name=name,
        description=payload.description,
        probability='M',
        impact='M',
        sort_order=count,
    )
    db.add(risk)
    db.commit()
    return _risk_out(risk, [])


@router.put('/risks/{risk_id}')
def update_risk(risk_id: str, payload: RiskUpdate, db: Session = Depends(get_db)):
    risk = db.query(models.Risk).filter_by(id=risk_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail='Risk not found')
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Risk name is required')
    _validate_level(payload.probability, 'probability')
    _validate_level(payload.impact, 'impact')

    risk.name = name
    risk.description = payload.description
    risk.probability = payload.probability
    risk.impact = payload.impact
    db.commit()
    mechanisms = db.query(models.RiskMechanism).filter_by(risk_id=risk_id).all()
    return _risk_out(risk, mechanisms)


@router.delete('/risks/{risk_id}')
def delete_risk(risk_id: str, db: Session = Depends(get_db)):
    risk = db.query(models.Risk).filter_by(id=risk_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail='Risk not found')
    db.query(models.RiskMechanism).filter_by(risk_id=risk_id).delete(synchronize_session=False)
    db.delete(risk)
    db.commit()
    return {'ok': True}


@router.post('/risks/{risk_id}/mechanisms')
def create_mechanism(risk_id: str, payload: MechanismCreate, db: Session = Depends(get_db)):
    risk = db.query(models.Risk).filter_by(id=risk_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail='Risk not found')
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Mechanism name is required')
    count = db.query(models.RiskMechanism).filter_by(risk_id=risk_id).count()
    mechanism = models.RiskMechanism(
        id=str(uuid.uuid4()),
        risk_id=risk_id,
        name=name,
        description=payload.description,
        capacity='M',
        cost='M',
        sort_order=count,
    )
    db.add(mechanism)
    db.commit()
    return _mechanism_out(mechanism)


@router.put('/mechanisms/{mechanism_id}')
def update_mechanism(mechanism_id: str, payload: MechanismUpdate, db: Session = Depends(get_db)):
    mechanism = db.query(models.RiskMechanism).filter_by(id=mechanism_id).first()
    if not mechanism:
        raise HTTPException(status_code=404, detail='Mechanism not found')
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Mechanism name is required')
    _validate_level(payload.capacity, 'capacity')
    _validate_level(payload.cost, 'cost')

    mechanism.name = name
    mechanism.description = payload.description
    mechanism.capacity = payload.capacity
    mechanism.cost = payload.cost
    db.commit()
    return _mechanism_out(mechanism)


@router.delete('/mechanisms/{mechanism_id}')
def delete_mechanism(mechanism_id: str, db: Session = Depends(get_db)):
    mechanism = db.query(models.RiskMechanism).filter_by(id=mechanism_id).first()
    if not mechanism:
        raise HTTPException(status_code=404, detail='Mechanism not found')
    db.delete(mechanism)
    db.commit()
    return {'ok': True}


# ---------------- Generate Plan (AI, background job — same pattern as
# country_profile: BackgroundTasks + marker files, since the API call takes
# real time and shouldn't die if the browser tab navigates away). ----------

def _plan_path(category_id: str) -> Path:
    return PLANS_DIR / f'{category_id}.md'


@router.get('/companies/{company_id}/risk-categories/{category_id}/plan')
def get_risk_plan(company_id: str, category_id: str, db: Session = Depends(get_db)):
    category = db.query(models.RiskCategory).filter_by(id=category_id, company_id=company_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Category not found')

    path = _plan_path(category_id)
    building = is_building(path)
    error = get_error(path)
    if not path.exists():
        return {'exists': False, 'building': building, 'error': error, 'content': None, 'generated_at': None}

    content = path.read_text(encoding='utf-8')
    generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return {'exists': True, 'building': building, 'error': error, 'content': content, 'generated_at': generated_at}


def _run_plan_build(company_id: str, category_id: str, company_name: str, category_name: str, risks_payload: list[dict]):
    path = _plan_path(category_id)
    try:
        body = generate_risk_plan(company_name, category_name, risks_payload)
        generated_at = datetime.now(timezone.utc)
        header = f'AI-generated — {generated_at.strftime("%B %d, %Y")}. Covers only risks assessed as well managed at generation time.\n\n'
        path.write_text(header + body, encoding='utf-8')
    except Exception as exc:  # noqa: BLE001 - must still clear the building marker either way
        mark_error(path, str(exc))
    finally:
        clear_building(path)


@router.post('/companies/{company_id}/risk-categories/{category_id}/generate-plan')
def generate_plan(company_id: str, category_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    category = db.query(models.RiskCategory).filter_by(id=category_id, company_id=company_id).first()
    if not category:
        raise HTTPException(status_code=404, detail='Category not found')

    company = db.query(models.Company).filter_by(id=company_id).first()
    company_name = company.name if company else company_id

    risks = db.query(models.Risk).filter_by(category_id=category_id).all()
    qualifying = []
    for risk in risks:
        mechanisms = db.query(models.RiskMechanism).filter_by(risk_id=risk.id).all()
        if is_well_managed(risk, mechanisms):
            qualifying.append(
                {
                    'name': risk.name,
                    'description': risk.description,
                    'mechanisms': [{'name': m.name, 'description': m.description} for m in mechanisms],
                }
            )

    if not qualifying:
        raise HTTPException(
            status_code=400,
            detail='No well-managed risks in this category yet — a risk needs enough mitigation mechanisms to outscore its exposure before it can go into an investor-facing plan.',
        )

    path = _plan_path(category_id)
    if is_building(path):
        return {'status': 'already_building'}

    mark_building(path)
    background_tasks.add_task(_run_plan_build, company_id, category_id, company_name, category.name, qualifying)
    return {'status': 'started', 'risks_included': len(qualifying)}
