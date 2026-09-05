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


def _get_or_create_year_salary(db: Session, record: models.PayrollRecord, projection_year: int):
    yearly_salary = db.query(models.PayrollYearlySalary).filter_by(
        payroll_record_id=record.id,
        projection_year=projection_year,
    ).first()

    if yearly_salary:
        return yearly_salary

    yearly_salary = models.PayrollYearlySalary(
        id=str(uuid.uuid4()),
        payroll_record_id=record.id,
        projection_year=projection_year,
        year_salary=record.year_salary,
    )
    db.add(yearly_salary)
    db.flush()
    return yearly_salary


def _get_effective_year_salary(db: Session, record: models.PayrollRecord, projection_year: int):
    selected_year_salary = db.query(models.PayrollYearlySalary).filter_by(
        payroll_record_id=record.id,
        projection_year=projection_year,
    ).first()
    if selected_year_salary:
        return selected_year_salary.year_salary

    previous_year_salary = (
        db.query(models.PayrollYearlySalary)
        .filter(
            models.PayrollYearlySalary.payroll_record_id == record.id,
            models.PayrollYearlySalary.projection_year <= projection_year,
        )
        .order_by(models.PayrollYearlySalary.projection_year.desc())
        .first()
    )
    if previous_year_salary:
        return previous_year_salary.year_salary

    return record.year_salary


def _get_year_growth_rate(db: Session, record: models.PayrollRecord, projection_year: int):
    """The raise % actually applied *for this specific year*, or None if none
    was. Unlike salary, this deliberately does not carry forward from an
    earlier year's override — each year's rate is independent, so applying a
    raise to Year 2 must never appear as Year 1's rate (or vice versa)."""
    yearly_salary = db.query(models.PayrollYearlySalary).filter_by(
        payroll_record_id=record.id,
        projection_year=projection_year,
    ).first()
    return yearly_salary.growth_rate_pct if yearly_salary else None


def _compute_levels(nodes, edges):
    children_by_parent = {}
    has_parent = set()

    for edge in edges:
        children_by_parent.setdefault(edge.source_node_id, []).append(edge.target_node_id)
        has_parent.add(edge.target_node_id)

    roots = [node.id for node in nodes if node.id not in has_parent]
    levels = {}
    queue = [(root_id, 0) for root_id in roots]

    while queue:
        node_id, level = queue.pop(0)
        if node_id in levels:
          continue
        levels[node_id] = level
        for child_id in children_by_parent.get(node_id, []):
            queue.append((child_id, level + 1))

    return levels


def _parent_map(edges):
    return {edge.target_node_id: edge.source_node_id for edge in edges}


def _next_sort_index(nodes, edges, company_id, parent_node_id=None):
    parent_map = _parent_map(edges)
    if parent_node_id:
        sibling_ids = [node.id for node in nodes if parent_map.get(node.id) == parent_node_id]
        sibling_nodes = [node for node in nodes if node.id in sibling_ids]
        return max((node.sort_index or 0.0 for node in sibling_nodes), default=0.0) + 1.0

    root_nodes = [node for node in nodes if node.id not in parent_map]
    return max((node.sort_index or 0.0 for node in root_nodes), default=0.0) + 1.0


def _ensure_payroll_record(db: Session, node: models.OrgChartNode):
    record = db.query(models.PayrollRecord).filter_by(org_chart_node_id=node.id).first()
    if record:
        return record

    record = models.PayrollRecord(
        id=str(uuid.uuid4()),
        org_chart_node_id=node.id,
        year_salary=0.0,
        start_date=date.today().isoformat(),
        start_projection_year=0,
    )
    db.add(record)
    db.flush()
    return record


def _employee_active_in_year(employee: models.PayrollEmployee, projection_year: int):
    if (employee.start_projection_year or 0) > projection_year:
        return False
    if employee.end_projection_year is not None and employee.end_projection_year < projection_year:
        return False
    return True


def _roster_for_node(db: Session, node_id: str):
    return (
        db.query(models.PayrollEmployee)
        .filter_by(org_chart_node_id=node_id)
        .order_by(models.PayrollEmployee.start_date)
        .all()
    )


def _headcount_for_node(db: Session, node_id: str, projection_year: int):
    roster = _roster_for_node(db, node_id)
    return sum(1 for employee in roster if _employee_active_in_year(employee, projection_year))


def _row_for_node(db: Session, node_id: str, projection_year: int | None = None):
    node = db.query(models.OrgChartNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail='Position not found')

    record = _ensure_payroll_record(db, node)
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(projection_year if projection_year is not None else 0, projection_years_limit)
    year_salary_value = _get_effective_year_salary(db, record, selected_projection_year)
    roster = _roster_for_node(db, node.id)
    headcount = sum(1 for employee in roster if _employee_active_in_year(employee, selected_projection_year))

    all_nodes = db.query(models.OrgChartNode).filter_by(company_id=node.company_id).all()
    all_edges = db.query(models.OrgChartEdge).filter_by(company_id=node.company_id).all()
    levels = _compute_levels(all_nodes, all_edges)
    parents = _parent_map(all_edges)

    return schemas.PayrollRowOut(
        node_id=node.id,
        office_name=node.office_name,
        employee_name=node.employee_name,
        area=node.area,
        parent_node_id=parents.get(node.id),
        level=levels.get(node.id, 0),
        sort_index=node.sort_index,
        projection_year=selected_projection_year,
        year_salary=year_salary_value,
        monthly_salary=round(year_salary_value / 12, 2),
        start_date=record.start_date,
        headcount=headcount,
        employees=roster,
        growth_rate_pct=_get_year_growth_rate(db, record, selected_projection_year),
    )


@router.get('/companies/{company_id}/payroll', response_model=list[schemas.PayrollRowOut])
def list_payroll(company_id: str, year: int = 0, db: Session = Depends(get_db)):
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    edges = db.query(models.OrgChartEdge).filter_by(company_id=company_id).all()
    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)

    records = {}
    rosters = {}
    for node in nodes:
        records[node.id] = _ensure_payroll_record(db, node)
        rosters[node.id] = _roster_for_node(db, node.id)

    levels = _compute_levels(nodes, edges)
    parents = _parent_map(edges)

    children_by_parent = {}
    for edge in edges:
        children_by_parent.setdefault(edge.source_node_id, []).append(edge.target_node_id)

    node_map = {node.id: node for node in nodes}
    for child_ids in children_by_parent.values():
        child_ids.sort(key=lambda node_id: (node_map[node_id].sort_index or 0.0, node_id))

    root_ids = [node.id for node in nodes if node.id not in parents]
    root_ids.sort(key=lambda node_id: (node_map[node_id].sort_index or 0.0, node_id))

    rows = []

    def visit(node_id: str, level: int):
        node = node_map[node_id]
        record = records[node.id]
        roster = rosters[node.id]
        headcount = sum(1 for employee in roster if _employee_active_in_year(employee, selected_projection_year))
        # A position only shows up for a year once someone is actually on it that year —
        # no placeholder rows for seats that haven't been hired yet.
        if headcount > 0:
            year_salary_value = _get_effective_year_salary(db, record, selected_projection_year)
            rows.append(
                schemas.PayrollRowOut(
                    node_id=node.id,
                    office_name=node.office_name,
                    employee_name=node.employee_name,
                    area=node.area,
                    parent_node_id=parents.get(node.id),
                    level=level,
                    sort_index=node.sort_index,
                    projection_year=selected_projection_year,
                    year_salary=year_salary_value,
                    monthly_salary=round(year_salary_value / 12, 2),
                    start_date=record.start_date,
                    headcount=headcount,
                    employees=roster,
                    growth_rate_pct=_get_year_growth_rate(db, record, selected_projection_year),
                )
            )
        for child_id in children_by_parent.get(node_id, []):
            visit(child_id, level + 1)

    for root_id in root_ids:
        visit(root_id, 0)

    db.commit()
    return rows


@router.get('/companies/{company_id}/payroll-areas', response_model=list[str])
def list_payroll_areas(company_id: str, db: Session = Depends(get_db)):
    # Year-independent on purpose: a position not yet hired in the viewed year
    # would otherwise vanish from the area suggestions along with its row.
    areas = (
        db.query(models.OrgChartNode.area)
        .filter(models.OrgChartNode.company_id == company_id, models.OrgChartNode.area.isnot(None))
        .distinct()
        .all()
    )
    return sorted({area for (area,) in areas if area})


@router.post('/companies/{company_id}/payroll-positions', response_model=schemas.PayrollRowOut)
def create_position(company_id: str, payload: schemas.PayrollPositionCreate, db: Session = Depends(get_db)):
    existing_nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    existing_edges = db.query(models.OrgChartEdge).filter_by(company_id=company_id).all()

    node = models.OrgChartNode(
        id=str(uuid.uuid4()),
        company_id=company_id,
        office_name=payload.office_name,
        employee_name=payload.employee_name,
        area=payload.area,
        position_x=0,
        position_y=0,
        sort_index=_next_sort_index(existing_nodes, existing_edges, company_id, payload.parent_node_id),
    )
    db.add(node)
    db.flush()

    if payload.parent_node_id:
        db.add(
            models.OrgChartEdge(
                id=str(uuid.uuid4()),
                company_id=company_id,
                source_node_id=payload.parent_node_id,
                target_node_id=node.id,
            )
        )

    record = models.PayrollRecord(
        id=str(uuid.uuid4()),
        org_chart_node_id=node.id,
        year_salary=payload.year_salary,
        start_date=payload.start_date,
        start_projection_year=0,
    )
    db.add(record)
    db.flush()

    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(payload.projection_year if payload.projection_year is not None else 0, projection_years_limit)
    selected_year_salary = _get_or_create_year_salary(db, record, selected_projection_year)
    selected_year_salary.year_salary = payload.year_salary
    record.year_salary = payload.year_salary
    record.start_projection_year = selected_projection_year

    db.add(
        models.PayrollEmployee(
            id=str(uuid.uuid4()),
            org_chart_node_id=node.id,
            employee_name=payload.employee_name,
            start_date=payload.start_date,
            start_projection_year=selected_projection_year,
        )
    )

    db.commit()

    return _row_for_node(db, node.id, selected_projection_year)


@router.patch('/payroll-positions/{node_id}', response_model=schemas.PayrollRowOut)
def update_position(node_id: str, payload: schemas.PayrollPositionUpdate, db: Session = Depends(get_db)):
    node = db.query(models.OrgChartNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail='Position not found')

    updates = payload.model_dump(exclude_unset=True)
    if 'office_name' in updates:
        node.office_name = updates['office_name']
    if 'area' in updates:
        node.area = updates['area']
    if 'parent_node_id' in updates:
        db.query(models.OrgChartEdge).filter_by(target_node_id=node_id).delete()
        parent_node_id = updates['parent_node_id']
        if parent_node_id:
            db.add(
                models.OrgChartEdge(
                    id=str(uuid.uuid4()),
                    company_id=node.company_id,
                    source_node_id=parent_node_id,
                    target_node_id=node_id,
                )
            )
            all_nodes = db.query(models.OrgChartNode).filter_by(company_id=node.company_id).all()
            all_edges = db.query(models.OrgChartEdge).filter_by(company_id=node.company_id).all()
            node.sort_index = _next_sort_index(all_nodes, all_edges, node.company_id, parent_node_id)
        else:
            all_nodes = db.query(models.OrgChartNode).filter_by(company_id=node.company_id).all()
            all_edges = db.query(models.OrgChartEdge).filter_by(company_id=node.company_id).all()
            node.sort_index = _next_sort_index(all_nodes, all_edges, node.company_id, None)

    if 'sort_index' in updates:
        node.sort_index = float(updates['sort_index'])

    record = db.query(models.PayrollRecord).filter_by(org_chart_node_id=node_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Payroll record not found')

    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(
        updates.get('projection_year') if updates.get('projection_year') is not None else 0,
        projection_years_limit,
    )
    record.start_projection_year = selected_projection_year

    if 'year_salary' in updates:
        selected_year_salary = _get_or_create_year_salary(db, record, selected_projection_year)
        selected_year_salary.year_salary = updates['year_salary']
        record.year_salary = updates['year_salary']

    db.commit()
    return _row_for_node(db, node_id, selected_projection_year)


def _apply_growth_rate_to_record(db: Session, record: models.PayrollRecord, rate_pct: float, target_year: int):
    """Sets the record's salary for the given year to (1 + rate%) of the
    *previous* year's salary, e.g. a 3% rate makes Year 2 equal to Year 1
    times 1.03. Anchoring on the previous year (not the target year's own,
    possibly already-raised value) is what makes this idempotent: changing
    the % and re-applying always recomputes from the same stable base
    instead of compounding on top of whatever was applied last time. Year 0
    has no previous year, so it bumps its own base salary directly. The rate
    itself is persisted on the *year's own* PayrollYearlySalary row, not on
    the position as a whole — otherwise applying a different rate to Year 2
    would silently overwrite Year 1's stored rate, since a position only has
    one of those rows per year but the record itself is shared across all of
    them."""
    if target_year == 0:
        new_salary = round(record.year_salary * (1 + rate_pct / 100), 2)
        record.year_salary = new_salary
    else:
        base_salary = _get_effective_year_salary(db, record, target_year - 1)
        new_salary = round(base_salary * (1 + rate_pct / 100), 2)

    yearly_salary = _get_or_create_year_salary(db, record, target_year)
    yearly_salary.year_salary = new_salary
    yearly_salary.growth_rate_pct = rate_pct


def _clear_growth_rate_from_record(db: Session, record: models.PayrollRecord, target_year: int):
    """Reverses whatever raise is applied for this year: drops the explicit
    override so the year falls back to inheriting the previous year's salary
    again, taking its stored rate down with it."""
    if target_year == 0:
        return
    db.query(models.PayrollYearlySalary).filter_by(
        payroll_record_id=record.id,
        projection_year=target_year,
    ).delete()


@router.post('/companies/{company_id}/apply-growth-rate-all', response_model=list[schemas.PayrollRowOut])
def apply_growth_rate_all(company_id: str, payload: schemas.PayrollGrowthApply, year: int = 0, db: Session = Depends(get_db)):
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    projection_years_limit = _get_projection_years_limit(db)
    target_year = _clamp_projection_year(year, projection_years_limit)

    for node in nodes:
        record = db.query(models.PayrollRecord).filter_by(org_chart_node_id=node.id).first()
        if not record:
            continue
        _apply_growth_rate_to_record(db, record, payload.rate_pct, target_year)

    db.commit()
    return list_payroll(company_id, target_year, db)


@router.post('/companies/{company_id}/clear-growth-rate', response_model=list[schemas.PayrollRowOut])
def clear_growth_rate(company_id: str, year: int = 0, db: Session = Depends(get_db)):
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    projection_years_limit = _get_projection_years_limit(db)
    target_year = _clamp_projection_year(year, projection_years_limit)

    for node in nodes:
        record = db.query(models.PayrollRecord).filter_by(org_chart_node_id=node.id).first()
        if not record:
            continue
        _clear_growth_rate_from_record(db, record, target_year)

    db.commit()
    return list_payroll(company_id, target_year, db)


@router.get('/payroll-positions/{node_id}/employees', response_model=list[schemas.PayrollEmployeeOut])
def list_employees(node_id: str, db: Session = Depends(get_db)):
    node = db.query(models.OrgChartNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail='Position not found')
    return _roster_for_node(db, node_id)


@router.post('/payroll-positions/{node_id}/employees', response_model=schemas.PayrollRowOut)
def add_employee(node_id: str, payload: schemas.PayrollEmployeeCreate, year: int = 0, db: Session = Depends(get_db)):
    node = db.query(models.OrgChartNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail='Position not found')

    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)

    db.add(
        models.PayrollEmployee(
            id=str(uuid.uuid4()),
            org_chart_node_id=node_id,
            employee_name=payload.employee_name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            start_projection_year=selected_projection_year,
            reports_to_node_id=payload.reports_to_node_id,
            area=payload.area,
        )
    )
    db.commit()
    return _row_for_node(db, node_id, selected_projection_year)


@router.patch('/payroll-employees/{employee_id}', response_model=schemas.PayrollRowOut)
def update_employee(employee_id: str, payload: schemas.PayrollEmployeeUpdate, year: int = 0, db: Session = Depends(get_db)):
    employee = db.query(models.PayrollEmployee).filter_by(id=employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail='Employee not found')

    updates = payload.model_dump(exclude_unset=True)
    if 'employee_name' in updates:
        employee.employee_name = updates['employee_name']
    if 'start_date' in updates:
        employee.start_date = updates['start_date']
    if 'end_date' in updates:
        employee.end_date = updates['end_date']
    if 'start_projection_year' in updates:
        employee.start_projection_year = updates['start_projection_year']
    if 'end_projection_year' in updates:
        employee.end_projection_year = updates['end_projection_year']
    if 'reports_to_node_id' in updates:
        employee.reports_to_node_id = updates['reports_to_node_id']
    if 'area' in updates:
        employee.area = updates['area']
    if 'position_x' in updates:
        employee.position_x = updates['position_x']
    if 'position_y' in updates:
        employee.position_y = updates['position_y']

    db.commit()

    projection_years_limit = _get_projection_years_limit(db)
    selected_projection_year = _clamp_projection_year(year, projection_years_limit)
    return _row_for_node(db, employee.org_chart_node_id, selected_projection_year)


@router.delete('/payroll-employees/{employee_id}')
def delete_employee(employee_id: str, db: Session = Depends(get_db)):
    employee = db.query(models.PayrollEmployee).filter_by(id=employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail='Employee not found')
    db.delete(employee)
    db.commit()
    return {'ok': True}
