"""
Generates the fillable payroll workbook for the "Download format" workflow:
download it, fill it in, and pick it back up via "Upload filled format" — a
plain download/upload round trip. This app and the spreadsheet editor don't
have to be on the same machine, and there's no background file watch to keep
alive across page navigation.

One row per position — Level drives compensation, so there's no per-employee
roster or per-year salary entry here. The Level reference table sits beside
the data as a lookup guide, in the same "Payroll" sheet rather than a
separate tab.
"""

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import PatternFill
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .payroll import _ensure_payroll_record, _get_year_payroll_level, _parent_map

router = APIRouter()

HEADER_STATIC = ['Position', 'Level', 'Area', 'Subordinated To']
REFERENCE_HEADER = ['Level', 'Yearly', 'Percentage', 'Monthly']
REFERENCE_START_COLUMN = 6  # column F, leaving column E blank as a spacer
REFERENCE_FILL = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')


def _build_workbook(db: Session, company_id: str) -> Workbook:
    nodes = db.query(models.OrgChartNode).filter_by(company_id=company_id).all()
    edges = db.query(models.OrgChartEdge).filter_by(company_id=company_id).all()
    parents = _parent_map(edges)
    node_by_id = {node.id: node for node in nodes}
    payroll_levels = db.query(models.PayrollLevel).order_by(models.PayrollLevel.sort_order).all()

    wb = Workbook()
    sheet = wb.active
    sheet.title = 'Payroll'

    for column, header in enumerate(HEADER_STATIC, start=1):
        sheet.cell(row=1, column=column, value=header).font = sheet.cell(row=1, column=column).font.copy(bold=True)

    sorted_nodes = sorted(nodes, key=lambda item: (item.sort_index or 0.0, item.office_name))
    for row_index, node in enumerate(sorted_nodes, start=2):
        parent_id = parents.get(node.id)
        parent_name = node_by_id[parent_id].office_name if parent_id in node_by_id else ''
        record = _ensure_payroll_record(db, node)
        level = _get_year_payroll_level(db, record, 0)
        sheet.cell(row=row_index, column=1, value=node.office_name)
        sheet.cell(row=row_index, column=2, value=level or '')
        sheet.cell(row=row_index, column=3, value=node.area or '')
        sheet.cell(row=row_index, column=4, value=parent_name)

    for column_offset, header in enumerate(REFERENCE_HEADER):
        column = REFERENCE_START_COLUMN + column_offset
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font = cell.font.copy(bold=True)
        cell.fill = REFERENCE_FILL

    for row_index, level in enumerate(payroll_levels, start=2):
        values = [level.level, level.yearly, level.percentage, level.monthly]
        for column_offset, value in enumerate(values):
            cell = sheet.cell(row=row_index, column=REFERENCE_START_COLUMN + column_offset, value=value)
            cell.fill = REFERENCE_FILL

    instructions = wb.create_sheet('Instructions')
    for line in [
        'How this file works',
        '',
        '- One row per position.',
        '- "Level" must exactly match a level from the reference table on the right (columns F-I) —',
        '  that\'s what sets this position\'s compensation for every projection year. Leave it blank',
        '  to leave the position\'s compensation unchanged.',
        '- "Subordinated To" must exactly match another row\'s "Position" text (or "Board of Directors", or',
        '  blank for the top of the chart).',
        '- Save the file, then use "Upload filled format" in the app to bring your changes in.',
    ]:
        instructions.append([line])

    sheet.column_dimensions['A'].width = 28
    sheet.column_dimensions['B'].width = 10
    sheet.column_dimensions['C'].width = 22
    sheet.column_dimensions['D'].width = 22
    sheet.column_dimensions['E'].width = 4
    sheet.column_dimensions['F'].width = 10
    sheet.column_dimensions['G'].width = 12
    sheet.column_dimensions['H'].width = 12
    sheet.column_dimensions['I'].width = 12

    return wb


@router.get('/companies/{company_id}/payroll-template')
def download_payroll_template(company_id: str, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    workbook = _build_workbook(db, company_id)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{company_id}-payroll-template.xlsx"'},
    )
