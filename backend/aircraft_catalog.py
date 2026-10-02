"""Majestic Cargo owns the fleet catalogue used by FRESH24 charter providers."""
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import Company


def aircraft_company_id(db: Session, company_id: str) -> str:
    company = db.get(Company, company_id)
    if company and company.name.lower().replace(' ', '') == 'fresh24':
        cargo = next((c for c in db.query(Company).all() if c.name.lower().replace(' ', '') == 'majesticcargo'), None)
        if cargo:
            return cargo.id
    return company_id


def uses_fleet_selection(db: Session, company_id: str) -> bool:
    owner = db.get(Company, aircraft_company_id(db, company_id))
    return bool(owner and owner.name.lower().replace(' ', '') == 'majesticcargo')


def migrate_aircraft_to_cargo(connection) -> None:
    companies = dict(connection.execute(text("SELECT lower(replace(name, ' ', '')), id FROM companies")).all())
    fresh, cargo = companies.get('fresh24'), companies.get('majesticcargo')
    if fresh and cargo:
        # Retain aircraft IDs so existing provider foreign keys remain valid.
        connection.execute(text('UPDATE logistics_aircraft SET company_id = :cargo WHERE company_id = :fresh'), {'cargo': cargo, 'fresh': fresh})
