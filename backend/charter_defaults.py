"""Persist Majestic Cargo's selected fleet as FRESH24 charter provider rows."""
import re
import uuid
from datetime import datetime, timezone
from sqlalchemy import inspect, text
from .models import Company, LogisticsAircraft, CharterProvider


def migrate_provider_fields(connection):
    inspector = inspect(connection)
    if not inspector.has_table('charter_providers'):
        return
    columns = inspector.get_columns('charter_providers')
    if any(c['name'] in ('main_base_iata','block_hour_cost') and not c['nullable'] for c in columns):
        sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='charter_providers'")).scalar_one()
        indexes = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='charter_providers' AND sql IS NOT NULL")).scalars().all()
        sql = re.sub(r'CREATE TABLE\s+["`\[]?charter_providers["`\]]?', 'CREATE TABLE charter_providers_nullable', sql, count=1, flags=re.I)
        for name in ('main_base_iata','block_hour_cost'):
            sql = re.sub(rf'({name}\s+\w+(?:\(\d+\))?)\s+NOT NULL',r'\1',sql,flags=re.I)
        connection.execute(text(sql))
        names = ', '.join('"'+c['name']+'"' for c in columns)
        connection.execute(text(f'INSERT INTO charter_providers_nullable ({names}) SELECT {names} FROM charter_providers'))
        connection.execute(text('DROP TABLE charter_providers'))
        connection.execute(text('ALTER TABLE charter_providers_nullable RENAME TO charter_providers'))
        for index in indexes:
            connection.execute(text(index))
    if 'source_company_id' not in {c['name'] for c in columns}:
        connection.execute(text('ALTER TABLE charter_providers ADD COLUMN source_company_id VARCHAR'))


def add_majestic_providers(db):
    companies = {c.name.lower().replace(' ',''):c for c in db.query(Company).all()}
    fresh,cargo = companies.get('fresh24'),companies.get('majesticcargo')
    if not fresh or not cargo:
        return []
    added = []
    for aircraft in db.query(LogisticsAircraft).filter_by(company_id=cargo.id,in_fleet=True).all():
        existing = db.query(CharterProvider).filter_by(company_id=fresh.id,aircraft_id=aircraft.id).all()
        if any(p.source_company_id==cargo.id or p.name.lower()==cargo.name.lower() for p in existing):
            continue
        provider = CharterProvider(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'charter/{fresh.id}/{cargo.id}/{aircraft.id}')),
            company_id=fresh.id,source_company_id=cargo.id,name=cargo.name,
            country_name=cargo.country_name or '',main_base_iata=None,
            aircraft_id=aircraft.id,block_hour_cost=None,provider_type='charter',
            created_at=datetime.now(timezone.utc).isoformat())
        db.add(provider)
        added.append(provider)
    db.flush()
    return added
