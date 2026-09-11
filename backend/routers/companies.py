import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or 'company'


class CompanyCreate(BaseModel):
    name: str
    logo: str = ''
    company_type: str
    company_dependency: str
    parent_company_id: str | None = None
    accent_from: str = '#35D399'
    accent_to: str = '#0EA5E9'
    country_name: str | None = None
    country_code: str | None = None
    currency_name: str | None = None
    currency_code: str | None = None


class CompanyOut(CompanyCreate):
    id: str
    logo: str | None = None

    class Config:
        from_attributes = True


class CompanyUpdate(BaseModel):
    name: str
    logo: str = ''
    company_type: str
    company_dependency: str
    parent_company_id: str | None = None
    accent_from: str = '#35D399'
    accent_to: str = '#0EA5E9'
    country_name: str | None = None
    country_code: str | None = None
    currency_name: str | None = None
    currency_code: str | None = None


@router.get('/companies', response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(models.Company).order_by(models.Company.id.asc()).all()


@router.post('/companies', response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company_id = f"{_slugify(payload.name)}-{int(time.time() * 1000)}"
    db_company = models.Company(
        id=company_id,
        name=payload.name,
        logo=payload.logo or '',
        company_type=payload.company_type,
        company_dependency=payload.company_dependency,
        parent_company_id=payload.parent_company_id,
        accent_from=payload.accent_from or '#35D399',
        accent_to=payload.accent_to or '#0EA5E9',
        country_name=payload.country_name,
        country_code=payload.country_code,
        currency_name=payload.currency_name,
        currency_code=payload.currency_code,
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


@router.put('/companies/{company_id}', response_model=CompanyOut)
def update_company(company_id: str, payload: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    company.name = payload.name
    company.logo = payload.logo or ''
    company.company_type = payload.company_type
    company.company_dependency = payload.company_dependency
    company.parent_company_id = payload.parent_company_id
    company.accent_from = payload.accent_from or '#35D399'
    company.accent_to = payload.accent_to or '#0EA5E9'
    company.country_name = payload.country_name
    company.country_code = payload.country_code
    company.currency_name = payload.currency_name
    company.currency_code = payload.currency_code
    db.commit()
    db.refresh(company)
    return company


@router.delete('/companies/{company_id}')
def delete_company(company_id: str, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    node_ids = [node.id for node in db.query(models.OrgChartNode).filter_by(company_id=company_id).all()]
    if node_ids:
        payroll_records = db.query(models.PayrollRecord).filter(models.PayrollRecord.org_chart_node_id.in_(node_ids)).all()
        payroll_record_ids = [record.id for record in payroll_records]
        if payroll_record_ids:
            db.query(models.PayrollYearlySalary).filter(
                models.PayrollYearlySalary.payroll_record_id.in_(payroll_record_ids)
            ).delete(synchronize_session=False)
        db.query(models.PayrollRecord).filter(models.PayrollRecord.org_chart_node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(models.PayrollEmployee).filter(models.PayrollEmployee.org_chart_node_id.in_(node_ids)).delete(synchronize_session=False)

    db.query(models.OrgChartEdge).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.OrgChartNode).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.RoadmapTask).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.CommercialBranch).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.CommercialCountry).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.CommercialRegion).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.ExpenseEntry).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.CommercialOperationEntry).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.SimParameter).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.RevenueStream).filter_by(company_id=company_id).delete(synchronize_session=False)
    journal_entry_ids = [row.id for row in db.query(models.JournalEntry).filter_by(company_id=company_id).all()]
    if journal_entry_ids:
        db.query(models.JournalLine).filter(models.JournalLine.journal_entry_id.in_(journal_entry_ids)).delete(synchronize_session=False)
    db.query(models.JournalEntry).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.GeneralLedgerAccount).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.StartupInvestmentRecord).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.StartupInvestmentPlan).filter_by(company_id=company_id).delete(synchronize_session=False)
    db.query(models.Company).filter_by(parent_company_id=company_id).update(
        {models.Company.parent_company_id: None}, synchronize_session=False
    )
    db.delete(company)
    db.commit()
    return {'ok': True}