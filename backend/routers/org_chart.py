import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from .. import schemas

router = APIRouter()


def _get_projection_years_limit(db: Session):
    settings = db.query(models.PortfolioSettings).filter_by(id='singleton').first()
    if not settings or not settings.projection_years:
        return 5
    return max(5, min(10, settings.projection_years))


def _clamp_projection_year(year: int, max_projection_years: int):
    if year < 0:
        return 0
    if year > max_projection_years:
        return max_projection_years
    return year


def _visible_node_ids(db: Session, company_id: str, selected_projection_year: int):
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    node_ids = [node.id for node in nodes]
    if not node_ids:
        return set(), []

    payroll_records = db.query(models.PayrollRecord).filter(
        models.PayrollRecord.org_chart_node_id.in_(node_ids)
    ).all()
    start_year_by_node = {
        record.org_chart_node_id: (record.start_projection_year or 0)
        for record in payroll_records
    }

    visible_nodes = [
        node for node in nodes
        if start_year_by_node.get(node.id, 0) <= selected_projection_year
    ]
    visible_node_ids = {node.id for node in visible_nodes}
    return visible_node_ids, visible_nodes


@router.get('/companies/{company_id}/org-chart-nodes', response_model=list[schemas.OrgChartNodeOut])
def list_nodes(company_id: str, year: int = 0, db: Session = Depends(get_db)):
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)
    _, visible_nodes = _visible_node_ids(db, company_id, selected_projection_year)
    return visible_nodes


@router.post('/companies/{company_id}/org-chart-nodes', response_model=schemas.OrgChartNodeOut)
def create_node(company_id: str, node: schemas.OrgChartNodeCreate, year: int = 0, db: Session = Depends(get_db)):
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)

    db_node = models.OrgChartNode(id=str(uuid.uuid4()), company_id=company_id, **node.model_dump())
    db.add(db_node)
    db.flush()

    db_record = models.PayrollRecord(
        id=str(uuid.uuid4()),
        org_chart_node_id=db_node.id,
        year_salary=0.0,
        start_date=date.today().isoformat(),
        start_projection_year=selected_projection_year,
    )
    db.add(db_record)

    db.commit()
    db.refresh(db_node)
    return db_node


@router.patch('/org-chart-nodes/{node_id}', response_model=schemas.OrgChartNodeOut)
def update_node(node_id: str, updates: schemas.OrgChartNodeUpdate, db: Session = Depends(get_db)):
    db_node = db.query(models.OrgChartNode).filter_by(id=node_id).first()
    if not db_node:
        raise HTTPException(status_code=404, detail='Node not found')

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_node, field, value)

    db.commit()
    db.refresh(db_node)
    return db_node


@router.delete('/org-chart-nodes/{node_id}')
def delete_node(node_id: str, db: Session = Depends(get_db)):
    payroll_record = db.query(models.PayrollRecord).filter_by(org_chart_node_id=node_id).first()
    if payroll_record:
        db.query(models.PayrollYearlySalary).filter_by(payroll_record_id=payroll_record.id).delete()
        db.delete(payroll_record)
    db.query(models.PayrollEmployee).filter_by(org_chart_node_id=node_id).delete()

    db.query(models.OrgChartEdge).filter(
        (models.OrgChartEdge.source_node_id == node_id)
        | (models.OrgChartEdge.target_node_id == node_id)
    ).delete()
    db.query(models.OrgChartNode).filter_by(id=node_id).delete()
    db.commit()
    return {'ok': True}


@router.get('/companies/{company_id}/org-chart-edges', response_model=list[schemas.OrgChartEdgeOut])
def list_edges(company_id: str, year: int = 0, db: Session = Depends(get_db)):
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)
    visible_node_ids, _ = _visible_node_ids(db, company_id, selected_projection_year)
    if not visible_node_ids:
        return []

    return db.query(models.OrgChartEdge).filter(
        models.OrgChartEdge.company_id == company_id,
        models.OrgChartEdge.source_node_id.in_(visible_node_ids),
        models.OrgChartEdge.target_node_id.in_(visible_node_ids),
    ).all()


@router.post('/companies/{company_id}/org-chart-edges', response_model=schemas.OrgChartEdgeOut)
def create_edge(company_id: str, edge: schemas.OrgChartEdgeCreate, db: Session = Depends(get_db)):
    db_edge = models.OrgChartEdge(id=str(uuid.uuid4()), company_id=company_id, **edge.model_dump())
    db.add(db_edge)
    db.commit()
    db.refresh(db_edge)
    return db_edge


@router.delete('/org-chart-edges/{edge_id}')
def delete_edge(edge_id: str, db: Session = Depends(get_db)):
    db.query(models.OrgChartEdge).filter_by(id=edge_id).delete()
    db.commit()
    return {'ok': True}
