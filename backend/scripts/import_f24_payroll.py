"""
One-off verification script: imports the F24-Payroll.xlsx 5-year hiring plan
into a real company, through the same SQLAlchemy models/session the app
uses, to prove the new payroll-roster schema persists correctly and that
Org Chart nodes/edges build from it as expected.

Run from the repo root:
    python -m backend.scripts.import_f24_payroll

Re-running is safe: it deletes and recreates the same test company (id
'f24-import-test') each time.
"""

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend import models  # noqa: E402

COMPANY_ID = 'f24-import-test'
COMPANY_NAME = 'FRESH24 — F24 Import Test'

# Derived from D:/OneDrive/xproject/payroll test file.xlsx (sheet 'F24-Payroll'):
# a headcount-by-month table for 24 roles across 5 years, plus a per-role
# yearly-comp table with a 3% built-in annual raise. Employee hire events are
# reconstructed from month-over-month headcount increases.
POSITIONS = [{"name": "CEO", "area": "Executive", "reports_to": None, "comp_by_year": [240000, 247200, 254616, 262254.48, 270122.11]}, {"name": "COO", "area": "Executive", "reports_to": "CEO", "comp_by_year": [204000, 210120, 216423.6, 222916.31, 229603.8]}, {"name": "CFO", "area": "Executive", "reports_to": "CEO", "comp_by_year": [180000, 185400, 190962, 196690.86, 202591.59]}, {"name": "CGC", "area": "Executive", "reports_to": "CEO", "comp_by_year": [120000, 123600, 127308, 131127.24, 135061.06]}, {"name": "CTO", "area": "Executive", "reports_to": "CEO", "comp_by_year": [120000, 123600, 127308, 131127.24, 135061.06]}, {"name": "Supply chain Director", "area": "Supply Chain", "reports_to": "COO", "comp_by_year": [90000, 92700, 95481, 98345.43, 101295.79]}, {"name": "Regulation /Certification Manager", "area": "Compliance", "reports_to": "CGC", "comp_by_year": [60000, 61800, 63654, 65563.62, 67530.53]}, {"name": "Colombia Product supply Manager", "area": "Supply Chain", "reports_to": "Supply chain Director", "comp_by_year": [60000, 61800, 63654, 65563.62, 67530.53]}, {"name": "CCO", "area": "Executive", "reports_to": "CEO", "comp_by_year": [120000, 123600, 127308, 131127.24, 135061.06]}, {"name": "Sales and Busines dev. Director", "area": "Sales & BD", "reports_to": "CCO", "comp_by_year": [90000, 92700, 95481, 98345.43, 101295.79]}, {"name": "Sales Rep.", "area": "Sales & BD", "reports_to": "Sales and Busines dev. Director", "comp_by_year": [60000, 61800, 63654, 65563.62, 67530.53]}, {"name": "Inventory Manager", "area": "Supply Chain", "reports_to": "Supply chain Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Safety compliance officer", "area": "Compliance", "reports_to": "CGC", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Air Logistic Manager", "area": "Logistics", "reports_to": "Supply chain Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Ground Logistic Manager", "area": "Logistics", "reports_to": "Supply chain Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "USA Product Suply Manager", "area": "Supply Chain", "reports_to": "Supply chain Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Infrastructure manager", "area": "Logistics", "reports_to": "COO", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Import / export Manager", "area": "Supply Chain", "reports_to": "Supply chain Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Admin Director", "area": "Admin & HR", "reports_to": "COO", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Human Resources Director", "area": "Admin & HR", "reports_to": "Admin Director", "comp_by_year": [66000, 67980, 70019.4, 72119.98, 74283.58]}, {"name": "Col product supply assistant", "area": "Supply Chain", "reports_to": "Colombia Product supply Manager", "comp_by_year": [40000, 41200, 42436, 43709.08, 45020.35]}, {"name": "Island destination Coordinator", "area": "Sales & BD", "reports_to": "Sales and Busines dev. Director", "comp_by_year": [90000, 92700, 95481, 98345.43, 101295.79]}, {"name": "Tech Developer", "area": "Technology", "reports_to": "CTO", "comp_by_year": [90000, 92700, 95481, 98345.43, 101295.79]}, {"name": "Logistic support", "area": "Logistics", "reports_to": "Air Logistic Manager", "comp_by_year": [45000, 46350, 47740.5, 49172.72, 50647.9]}]

EMPLOYEES = [{"position": "CEO", "year_index": 0, "month_index": 0}, {"position": "COO", "year_index": 0, "month_index": 0}, {"position": "CFO", "year_index": 0, "month_index": 0}, {"position": "CGC", "year_index": 0, "month_index": 0}, {"position": "CTO", "year_index": 0, "month_index": 0}, {"position": "Supply chain Director", "year_index": 0, "month_index": 0}, {"position": "Regulation /Certification Manager", "year_index": 0, "month_index": 0}, {"position": "Regulation /Certification Manager", "year_index": 1, "month_index": 0}, {"position": "Colombia Product supply Manager", "year_index": 0, "month_index": 0}, {"position": "Colombia Product supply Manager", "year_index": 1, "month_index": 0}, {"position": "Colombia Product supply Manager", "year_index": 1, "month_index": 0}, {"position": "CCO", "year_index": 0, "month_index": 0}, {"position": "Sales and Busines dev. Director", "year_index": 0, "month_index": 0}, {"position": "Sales Rep.", "year_index": 0, "month_index": 0}, {"position": "Sales Rep.", "year_index": 0, "month_index": 3}, {"position": "Sales Rep.", "year_index": 0, "month_index": 9}, {"position": "Sales Rep.", "year_index": 2, "month_index": 0}, {"position": "Sales Rep.", "year_index": 2, "month_index": 0}, {"position": "Sales Rep.", "year_index": 2, "month_index": 0}, {"position": "Inventory Manager", "year_index": 0, "month_index": 0}, {"position": "Inventory Manager", "year_index": 1, "month_index": 0}, {"position": "Inventory Manager", "year_index": 1, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 0, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 1, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 1, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 1, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 1, "month_index": 0}, {"position": "Safety compliance officer", "year_index": 1, "month_index": 0}, {"position": "Air Logistic Manager", "year_index": 0, "month_index": 0}, {"position": "Air Logistic Manager", "year_index": 1, "month_index": 0}, {"position": "Air Logistic Manager", "year_index": 1, "month_index": 0}, {"position": "Ground Logistic Manager", "year_index": 0, "month_index": 0}, {"position": "Ground Logistic Manager", "year_index": 1, "month_index": 0}, {"position": "Ground Logistic Manager", "year_index": 1, "month_index": 0}, {"position": "USA Product Suply Manager", "year_index": 0, "month_index": 0}, {"position": "USA Product Suply Manager", "year_index": 1, "month_index": 0}, {"position": "USA Product Suply Manager", "year_index": 1, "month_index": 0}, {"position": "Infrastructure manager", "year_index": 0, "month_index": 0}, {"position": "Infrastructure manager", "year_index": 1, "month_index": 0}, {"position": "Infrastructure manager", "year_index": 1, "month_index": 0}, {"position": "Import / export Manager", "year_index": 0, "month_index": 0}, {"position": "Import / export Manager", "year_index": 1, "month_index": 0}, {"position": "Import / export Manager", "year_index": 1, "month_index": 0}, {"position": "Admin Director", "year_index": 0, "month_index": 0}, {"position": "Human Resources Director", "year_index": 0, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 6}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 6}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 6}, {"position": "Col product supply assistant", "year_index": 0, "month_index": 6}, {"position": "Col product supply assistant", "year_index": 1, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 1, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 1, "month_index": 0}, {"position": "Col product supply assistant", "year_index": 1, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 3}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 3}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 3}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 3}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 9}, {"position": "Island destination Coordinator", "year_index": 0, "month_index": 9}, {"position": "Island destination Coordinator", "year_index": 1, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 1, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 1, "month_index": 0}, {"position": "Island destination Coordinator", "year_index": 1, "month_index": 0}, {"position": "Tech Developer", "year_index": 0, "month_index": 0}, {"position": "Tech Developer", "year_index": 0, "month_index": 0}, {"position": "Tech Developer", "year_index": 0, "month_index": 0}, {"position": "Tech Developer", "year_index": 0, "month_index": 9}, {"position": "Tech Developer", "year_index": 0, "month_index": 9}, {"position": "Logistic support", "year_index": 0, "month_index": 3}, {"position": "Logistic support", "year_index": 0, "month_index": 3}, {"position": "Logistic support", "year_index": 0, "month_index": 9}, {"position": "Logistic support", "year_index": 0, "month_index": 9}]

FICTITIOUS_EPOCH = date(1, 1, 1)
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = DAYS_PER_MONTH * 12


def sim_iso_date(sim_year: int, month_index: int) -> str:
    """Mirrors src/components/shared/SimulationCalendar/simulationCalendarMath.js
    (30-day months, 360-day years from 0001-01-01) so dates display correctly
    under this portfolio's 'simulation' calendar mode."""
    elapsed_days = sim_year * DAYS_PER_YEAR + month_index * DAYS_PER_MONTH
    return (FICTITIOUS_EPOCH + timedelta(days=elapsed_days)).isoformat()


def wipe_existing_company(db):
    node_ids = [row[0] for row in db.query(models.OrgChartNode.id).filter_by(company_id=COMPANY_ID).all()]
    if node_ids:
        record_ids = [
            row[0] for row in db.query(models.PayrollRecord.id).filter(
                models.PayrollRecord.org_chart_node_id.in_(node_ids)
            ).all()
        ]
        if record_ids:
            db.query(models.PayrollYearlySalary).filter(
                models.PayrollYearlySalary.payroll_record_id.in_(record_ids)
            ).delete(synchronize_session=False)
        db.query(models.PayrollRecord).filter(
            models.PayrollRecord.org_chart_node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.PayrollEmployee).filter(
            models.PayrollEmployee.org_chart_node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.OrgChartEdge).filter_by(company_id=COMPANY_ID).delete(synchronize_session=False)
        db.query(models.OrgChartNode).filter_by(company_id=COMPANY_ID).delete(synchronize_session=False)
    db.query(models.Company).filter_by(id=COMPANY_ID).delete(synchronize_session=False)
    db.commit()


def run_import():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        wipe_existing_company(db)

        db.add(models.Company(
            id=COMPANY_ID,
            name=COMPANY_NAME,
            logo='',
            company_type='LLC',
            company_dependency='Stand-alone',
            parent_company_id=None,
            accent_from='#35D399',
            accent_to='#0EA5E9',
        ))
        db.flush()

        node_id_by_name = {p['name']: str(uuid.uuid4()) for p in POSITIONS}

        for index, position in enumerate(POSITIONS):
            node = models.OrgChartNode(
                id=node_id_by_name[position['name']],
                company_id=COMPANY_ID,
                office_name=position['name'],
                employee_name=None,
                area=position['area'],
                position_x=(index % 6) * 220,
                position_y=(index // 6) * 160,
                sort_index=float(index),
            )
            db.add(node)

            record = models.PayrollRecord(
                id=str(uuid.uuid4()),
                org_chart_node_id=node.id,
                year_salary=position['comp_by_year'][0],
                start_date=sim_iso_date(0, 0),
                start_projection_year=1,
            )
            db.add(record)
            db.flush()

            for year_offset, year_salary in enumerate(position['comp_by_year']):
                db.add(models.PayrollYearlySalary(
                    id=str(uuid.uuid4()),
                    payroll_record_id=record.id,
                    projection_year=year_offset + 1,
                    year_salary=year_salary,
                ))

        for position in POSITIONS:
            if position['reports_to']:
                db.add(models.OrgChartEdge(
                    id=str(uuid.uuid4()),
                    company_id=COMPANY_ID,
                    source_node_id=node_id_by_name[position['reports_to']],
                    target_node_id=node_id_by_name[position['name']],
                ))

        for hire in EMPLOYEES:
            projection_year = hire['year_index'] + 1
            db.add(models.PayrollEmployee(
                id=str(uuid.uuid4()),
                org_chart_node_id=node_id_by_name[hire['position']],
                employee_name=None,
                start_date=sim_iso_date(hire['year_index'], hire['month_index']),
                end_date=None,
                start_projection_year=projection_year,
                end_projection_year=None,
            ))

        db.commit()
        print(f'Imported {len(POSITIONS)} positions, {len(EMPLOYEES)} hires, '
              f'{sum(1 for p in POSITIONS if p["reports_to"])} org-chart edges '
              f'into company "{COMPANY_NAME}" ({COMPANY_ID}).')
    finally:
        db.close()


if __name__ == '__main__':
    run_import()
