import base64
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()

LOGOS_DIR = Path(__file__).resolve().parent.parent / 'company_logos'
DATA_URL_RE = re.compile(r'^data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$', re.DOTALL)
SERVED_LOGO_RE = re.compile(r'^(?:https?://[^/]+)?/company-logos/(?P<filename>.+)$')


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or 'company'


def persist_logo(company_id: str, logo_value: str | None) -> str | None:
    """A logo is saved as a real file under company_logos/, not as a
    multi-hundred-KB base64 blob in the companies table — that's what made
    FRESH24's logo disappear in the first place (any edit that round-tripped
    the row without resending the blob would silently drop it). Called on
    every create/update: a fresh upload (a data: URL from the browser's
    FileReader) gets decoded and written to disk; a URL the app already
    served back (unchanged on this edit) is normalized to a bare path so it
    stays portable across dev/prod origins; anything else (empty, or some
    other already-external URL) passes through untouched."""
    if not logo_value:
        return logo_value

    match = DATA_URL_RE.match(logo_value)
    if match:
        ext = match.group('ext').lower()
        if ext in ('jpeg', 'jpg'):
            ext = 'jpg'
        else:
            ext = re.sub(r'[^a-z0-9]', '', ext) or 'png'
        try:
            image_bytes = base64.b64decode(match.group('data'))
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=400, detail='Logo image data is not valid base64') from error

        LOGOS_DIR.mkdir(parents=True, exist_ok=True)
        for existing in LOGOS_DIR.glob(f'{company_id}.*'):
            existing.unlink(missing_ok=True)
        (LOGOS_DIR / f'{company_id}.{ext}').write_bytes(image_bytes)
        return f'/company-logos/{company_id}.{ext}'

    served_match = SERVED_LOGO_RE.match(logo_value)
    if served_match:
        return f'/company-logos/{served_match.group("filename")}'

    return logo_value


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
    phase_number: int | None = None


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
    phase_number: int | None = None


@router.get('/companies', response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(models.Company).order_by(models.Company.id.asc()).all()


@router.post('/companies', response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company_id = f"{_slugify(payload.name)}-{int(time.time() * 1000)}"
    db_company = models.Company(
        id=company_id,
        name=payload.name,
        logo=persist_logo(company_id, payload.logo) or '',
        company_type=payload.company_type,
        company_dependency=payload.company_dependency,
        parent_company_id=payload.parent_company_id,
        accent_from=payload.accent_from or '#35D399',
        accent_to=payload.accent_to or '#0EA5E9',
        country_name=payload.country_name,
        country_code=payload.country_code,
        currency_name=payload.currency_name,
        currency_code=payload.currency_code,
        phase_number=payload.phase_number,
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
    company.logo = persist_logo(company_id, payload.logo) or ''
    company.company_type = payload.company_type
    company.company_dependency = payload.company_dependency
    company.parent_company_id = payload.parent_company_id
    company.accent_from = payload.accent_from or '#35D399'
    company.accent_to = payload.accent_to or '#0EA5E9'
    company.country_name = payload.country_name
    company.country_code = payload.country_code
    company.currency_name = payload.currency_name
    company.currency_code = payload.currency_code
    company.phase_number = payload.phase_number
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