"""
Generates and serves the fillable payroll workbook used by the Payroll module's
"Download format" button. The workflow is: generate a template into a local
folder and open it in Excel, the user edits and saves it in place, and the
frontend polls /status to notice the save and pull the file back down for
import — no file-picker dialog on either side.
"""

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from ..database import PROJECT_ROOT, get_db
from .. import models
from .payroll import (
    _compute_levels,
    _ensure_payroll_record,
    _get_effective_year_salary,
    _get_projection_years_limit,
    _parent_map,
    _roster_for_node,
)

router = APIRouter()

TEMPLATES_DIR = PROJECT_ROOT / 'backend' / 'payroll_templates'

HEADER_STATIC = ['Position', 'Area', 'Subordinated To', 'Employee Name', 'Start Date', 'End Date']


def _template_path(company_id: str) -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR / f'{company_id}.xlsx'


def _build_workbook(db: Session, company_id: str) -> Workbook:
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    edges = db.query(models.OrgChartEdge).filter_by(company_id=company_id).all()
    parents = _parent_map(edges)
    node_by_id = {node.id: node for node in nodes}
    projection_years_limit = _get_projection_years_limit(db)
    year_headers = [f'Year {year} Salary' for year in range(projection_years_limit + 1)]

    wb = Workbook()
    sheet = wb.active
    sheet.title = 'Payroll'
    sheet.append(HEADER_STATIC + year_headers)
    for cell in sheet[1]:
        cell.font = cell.font.copy(bold=True)

    for node in sorted(nodes, key=lambda item: (item.sort_index or 0.0, item.office_name)):
        record = _ensure_payroll_record(db, node)
        comp_by_year = [_get_effective_year_salary(db, record, year) for year in range(projection_years_limit + 1)]
        parent_id = parents.get(node.id)
        parent_name = node_by_id[parent_id].office_name if parent_id in node_by_id else ''
        roster = _roster_for_node(db, node.id)

        rows = roster if roster else [None]
        for employee in rows:
            sheet.append([
                node.office_name,
                node.area or '',
                parent_name,
                (employee.employee_name if employee else '') or '',
                (employee.start_date if employee else '') or '',
                (employee.end_date if employee else '') or '',
                *comp_by_year,
            ])

    instructions = wb.create_sheet('Instructions')
    for line in [
        'How this file works',
        '',
        '- One row per person. Give the same "Position" text to every row that shares a role — that\'s what',
        '  groups them into one position with several hires instead of several separate positions.',
        '- Leave "Employee Name" blank for a vacant seat you\'re still budgeting for.',
        '- "Subordinated To" must exactly match another row\'s "Position" text (or "Board of Directors", or',
        '  blank for the top of the chart).',
        '- Dates are plain text in YYYY-MM-DD form.',
        '- The Year N Salary columns are per-employee pay for that position in that projection year — the',
        '  same figure repeats on every row for that position; edit any one of them and match the rest.',
        '- Save this file in place (Ctrl+S) when you\'re done — the app will notice and pull it in automatically.',
    ]:
        instructions.append([line])

    sheet.column_dimensions['A'].width = 28
    sheet.column_dimensions['B'].width = 18
    sheet.column_dimensions['C'].width = 22
    sheet.column_dimensions['D'].width = 22
    sheet.column_dimensions['E'].width = 14
    sheet.column_dimensions['F'].width = 14

    return wb


def _open_in_default_app(path: Path):
    try:
        if sys.platform.startswith('win'):
            os.startfile(str(path))  # noqa: S606 - local dev tool opening a file it just wrote
        elif sys.platform == 'darwin':
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except OSError:
        pass


@router.post('/companies/{company_id}/payroll-template')
def generate_payroll_template(company_id: str, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    workbook = _build_workbook(db, company_id)
    path = _template_path(company_id)
    workbook.save(path)
    _open_in_default_app(path)

    modified_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return {'ok': True, 'modified_at': modified_at}


@router.get('/companies/{company_id}/payroll-template/status')
def payroll_template_status(company_id: str):
    path = _template_path(company_id)
    if not path.exists():
        return {'exists': False, 'modified_at': None}
    return {'exists': True, 'modified_at': datetime.fromtimestamp(path.stat().st_mtime).isoformat()}


@router.get('/companies/{company_id}/payroll-template/file')
def payroll_template_file(company_id: str):
    path = _template_path(company_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail='No template has been generated for this company yet')
    return FileResponse(
        path,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=f'{company_id}-payroll-template.xlsx',
    )
