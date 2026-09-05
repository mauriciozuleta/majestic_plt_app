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


class CompanyOut(CompanyCreate):
    id: str
    logo: str | None = None

    class Config:
        from_attributes = True


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
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


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
    db.query(models.Company).filter_by(parent_company_id=company_id).update(
        {models.Company.parent_company_id: None}, synchronize_session=False
    )
    db.delete(company)
    db.commit()
    return {'ok': True}