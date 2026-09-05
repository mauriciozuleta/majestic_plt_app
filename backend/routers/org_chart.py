import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from .. import schemas
from .payroll import _employee_active_in_year, _roster_for_node

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


def _seat_node_id(employee_id: str) -> str:
    return f'seat-{employee_id}'


def _ordered_roster(db: Session, node_id: str, selected_projection_year: int):
    roster = [
        employee
        for employee in _roster_for_node(db, node_id)
        if _employee_active_in_year(employee, selected_projection_year)
    ]
    roster.sort(key=lambda employee: employee.start_date)
    return roster


def _seat_nodes_for_position(node, roster, company_id):
    """One box per seat instead of one box for the whole position — a
    Secretary position with 3 people reporting to 3 different managers must
    show 3 boxes, not 1 box with 3 lines coming out of it. Seats that have
    never been dragged inherit a staggered offset from the position's own
    saved spot so they don't all stack exactly on top of each other."""
    seat_nodes = []
    for index, employee in enumerate(roster):
        default_x = node.position_x + (index % 3) * 200
        default_y = node.position_y + 110 + (index // 3) * 90
        seat_nodes.append(
            schemas.OrgChartNodeOut(
                id=_seat_node_id(employee.id),
                company_id=company_id,
                office_name=f'{node.office_name} #{index + 1}',
                employee_name=employee.employee_name,
                area=employee.area or node.area,
                position_x=employee.position_x if employee.position_x is not None else default_x,
                position_y=employee.position_y if employee.position_y is not None else default_y,
                sort_index=node.sort_index,
            )
        )
    return seat_nodes


@router.get('/companies/{company_id}/org-chart-nodes', response_model=list[schemas.OrgChartNodeOut])
def list_nodes(company_id: str, year: int = 0, db: Session = Depends(get_db)):
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)
    _, visible_nodes = _visible_node_ids(db, company_id, selected_projection_year)

    result = []
    for node in visible_nodes:
        roster = _ordered_roster(db, node.id, selected_projection_year)
        if len(roster) > 1:
            result.extend(_seat_nodes_for_position(node, roster, company_id))
        else:
            result.append(node)
    return result


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
    """A position box only ever stores one "default" parent edge. For a
    split position, that's not enough — each seat gets its own box (see
    list_nodes) and needs its own line to whoever it actually reports to,
    which can differ per seat via the Matrix's "Reports To" column. So for
    a split node, this emits one edge per seat, targeting that seat's box
    id, instead of the position's single stored edge. Non-split positions
    are untouched: same single real, draggable/deletable OrgChartEdge as
    always. Seat edges use a virtual id (not backed by an OrgChartEdge row)
    since a seat's manager is stored on the employee, not as an edge row —
    change it from the Matrix or by dragging the seat's connector."""
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)
    visible_node_ids, visible_nodes = _visible_node_ids(db, company_id, selected_projection_year)
    if not visible_node_ids:
        return []

    stored_edges = db.query(models.OrgChartEdge).filter(
        models.OrgChartEdge.company_id == company_id,
        models.OrgChartEdge.source_node_id.in_(visible_node_ids),
        models.OrgChartEdge.target_node_id.in_(visible_node_ids),
    ).all()
    default_edge_by_node = {edge.target_node_id: edge for edge in stored_edges}

    result = []
    for node in visible_nodes:
        default_edge = default_edge_by_node.get(node.id)
        default_parent_id = default_edge.source_node_id if default_edge else None
        roster = _ordered_roster(db, node.id, selected_projection_year)

        if len(roster) > 1:
            for employee in roster:
                target = employee.reports_to_node_id or default_parent_id
                if not target or target not in visible_node_ids:
                    continue
                seat_id = _seat_node_id(employee.id)
                result.append(
                    schemas.OrgChartEdgeOut(
                        id=f'virtual-{seat_id}-{target}',
                        company_id=company_id,
                        source_node_id=target,
                        target_node_id=seat_id,
                    )
                )
            continue

        if not roster:
            if default_edge:
                result.append(default_edge)
            continue

        (only_employee,) = roster
        only_target = only_employee.reports_to_node_id or default_parent_id
        if not only_target or only_target not in visible_node_ids:
            continue
        if default_edge and default_parent_id == only_target:
            result.append(default_edge)
        else:
            result.append(
                schemas.OrgChartEdgeOut(
                    id=f'virtual-{node.id}-{only_target}',
                    company_id=company_id,
                    source_node_id=only_target,
                    target_node_id=node.id,
                )
            )

    return result


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
