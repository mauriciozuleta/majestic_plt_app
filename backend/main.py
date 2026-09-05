from datetime import date
import os
import sqlite3
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import Base, engine
from .routers import commercial_structure, companies, org_chart, payroll, payroll_template, roadmap, settings

Base.metadata.create_all(bind=engine)

EXTERNAL_COUNTRY_DB = r'D:\OneDrive\0. software Lab\AI_FRESH24\db.sqlite3'


def _ensure_schema_migrations():
    inspector = inspect(engine)
    with engine.begin() as connection:
        if 'portfolio_settings' in inspector.get_table_names():
            settings_columns = {column['name'] for column in inspector.get_columns('portfolio_settings')}
            if 'projection_years' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN projection_years INTEGER DEFAULT 5'))

        if 'org_chart_nodes' in inspector.get_table_names():
            node_columns = {column['name'] for column in inspector.get_columns('org_chart_nodes')}
            if 'sort_index' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN sort_index FLOAT DEFAULT 0.0'))
            if 'area' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN area VARCHAR'))

        if 'roadmap_tasks' in inspector.get_table_names():
            task_columns = {column['name'] for column in inspector.get_columns('roadmap_tasks')}
            if 'linked_company_id' not in task_columns:
                connection.execute(text('ALTER TABLE roadmap_tasks ADD COLUMN linked_company_id VARCHAR'))
            if 'responsible' not in task_columns:
                connection.execute(text("ALTER TABLE roadmap_tasks ADD COLUMN responsible VARCHAR DEFAULT ''"))
            if 'parent_task_id' not in task_columns:
                connection.execute(text('ALTER TABLE roadmap_tasks ADD COLUMN parent_task_id VARCHAR'))
            if 'sort_index' not in task_columns:
                connection.execute(text('ALTER TABLE roadmap_tasks ADD COLUMN sort_index FLOAT DEFAULT 0.0'))

        if 'payroll_records' in inspector.get_table_names():
            payroll_columns = {column['name'] for column in inspector.get_columns('payroll_records')}
            if 'start_projection_year' not in payroll_columns:
                connection.execute(text('ALTER TABLE payroll_records ADD COLUMN start_projection_year INTEGER DEFAULT 0'))

                # Backfill simulation dates (0001-based calendar) into projection years.
                records = connection.execute(text('SELECT id, start_date FROM payroll_records')).fetchall()
                simulation_epoch = date(1, 1, 1)
                for record_id, start_date in records:
                    start_projection_year = 0
                    try:
                        stored_date = date.fromisoformat(start_date)
                        if stored_date.year < 1900:
                            elapsed_days = (stored_date - simulation_epoch).days
                            start_projection_year = max(0, elapsed_days // 360)
                    except (TypeError, ValueError):
                        start_projection_year = 0

                    connection.execute(
                        text('UPDATE payroll_records SET start_projection_year = :start_projection_year WHERE id = :record_id'),
                        {
                            'start_projection_year': start_projection_year,
                            'record_id': record_id,
                        },
                    )

        if 'payroll_yearly_salaries' in inspector.get_table_names():
            yearly_columns = {column['name'] for column in inspector.get_columns('payroll_yearly_salaries')}
            if 'projection_year' not in yearly_columns:
                connection.execute(text('ALTER TABLE payroll_yearly_salaries ADD COLUMN projection_year INTEGER DEFAULT 1'))
            if 'year_salary' not in yearly_columns:
                connection.execute(text('ALTER TABLE payroll_yearly_salaries ADD COLUMN year_salary FLOAT DEFAULT 0.0'))
            if 'growth_rate_pct' not in yearly_columns:
                connection.execute(text('ALTER TABLE payroll_yearly_salaries ADD COLUMN growth_rate_pct FLOAT'))

        if 'payroll_employees' in inspector.get_table_names():
            employee_columns = {column['name'] for column in inspector.get_columns('payroll_employees')}
            if 'reports_to_node_id' not in employee_columns:
                connection.execute(text('ALTER TABLE payroll_employees ADD COLUMN reports_to_node_id VARCHAR'))
            if 'area' not in employee_columns:
                connection.execute(text('ALTER TABLE payroll_employees ADD COLUMN area VARCHAR'))
            if 'position_x' not in employee_columns:
                connection.execute(text('ALTER TABLE payroll_employees ADD COLUMN position_x INTEGER'))
            if 'position_y' not in employee_columns:
                connection.execute(text('ALTER TABLE payroll_employees ADD COLUMN position_y INTEGER'))

        if 'commercial_countries' in inspector.get_table_names():
            commercial_country_columns = {column['name'] for column in inspector.get_columns('commercial_countries')}
            if 'country_code' not in commercial_country_columns:
                connection.execute(text('ALTER TABLE commercial_countries ADD COLUMN country_code VARCHAR'))
            if 'currency' not in commercial_country_columns:
                connection.execute(text('ALTER TABLE commercial_countries ADD COLUMN currency VARCHAR'))
            if 'currency_code' not in commercial_country_columns:
                connection.execute(text('ALTER TABLE commercial_countries ADD COLUMN currency_code VARCHAR'))

        if 'country_reference_catalog' in inspector.get_table_names():
            country_rows: list[tuple[str, str, str, str, str]] = []
            if os.path.exists(EXTERNAL_COUNTRY_DB):
                source_db = sqlite3.connect(EXTERNAL_COUNTRY_DB)
                try:
                    cursor = source_db.cursor()
                    cursor.execute(
                        """
                        SELECT name, country_code, currency, currency_code, region
                        FROM main_country
                        ORDER BY name
                        """
                    )
                    country_rows = cursor.fetchall()
                finally:
                    source_db.close()

            if not country_rows:
                current_count = connection.execute(text('SELECT COUNT(*) FROM country_reference_catalog')).scalar() or 0
                if current_count == 0:
                    country_rows = [
                        ('Bahamas', 'BS', 'Bahamian Dollar', 'BSD', 'Caribbean'),
                        ('Bermuda', 'BM', 'Bermudian Dollar', 'BMD', 'North America'),
                        ('Colombia', 'CO', 'Colombian Peso', 'COP', 'South-Central America'),
                        ('Netherlands Antilles', 'AN', 'Netherlands Antillean Guilder', 'ANG', 'Caribbean'),
                        ('United States', 'US', 'US Dollar', 'USD', 'North America'),
                    ]

            for name, country_code, currency, currency_code, region in country_rows:
                if not country_code or not region:
                    continue
                connection.execute(
                    text(
                        """
                        INSERT INTO country_reference_catalog
                        (id, name, country_code, currency, currency_code, region)
                        VALUES (:id, :name, :country_code, :currency, :currency_code, :region)
                        ON CONFLICT(country_code) DO UPDATE SET
                            name = excluded.name,
                            currency = excluded.currency,
                            currency_code = excluded.currency_code,
                            region = excluded.region
                        """
                    ),
                    {
                        'id': str(uuid.uuid4()),
                        'name': name,
                        'country_code': country_code,
                        'currency': currency,
                        'currency_code': currency_code,
                        'region': region,
                    },
                )


_ensure_schema_migrations()

app = FastAPI(title='MAJESTIC P.L.T. API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:5174'],
    allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(roadmap.router)
app.include_router(settings.router)
app.include_router(companies.router)
app.include_router(org_chart.router)
app.include_router(payroll.router)
app.include_router(payroll_template.router)
app.include_router(commercial_structure.router)
