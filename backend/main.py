from datetime import date
import os
import sqlite3
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import Base, engine
from .routers import (
    commercial_structure,
    companies,
    expense_categories,
    org_chart,
    payroll,
    payroll_levels,
    payroll_template,
    roadmap,
    settings,
)

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
            if 'payroll_level' not in yearly_columns:
                connection.execute(text('ALTER TABLE payroll_yearly_salaries ADD COLUMN payroll_level VARCHAR'))

        if 'payroll_levels' in inspector.get_table_names():
            level_count = connection.execute(text('SELECT COUNT(*) FROM payroll_levels')).scalar() or 0
            if level_count == 0:
                default_levels = [
                    ('C1', 480000.0, 100.0, 40000.0),
                    ('C2', 432000.0, 90.0, 36000.0),
                    ('C3', 384000.0, 80.0, 32000.0),
                    ('D1', 336000.0, 70.0, 28000.0),
                    ('D2', 288000.0, 60.0, 24000.0),
                    ('D3', 240000.0, 50.0, 20000.0),
                    ('D4', 192000.0, 40.0, 16000.0),
                    ('E1', 144000.0, 30.0, 12000.0),
                    ('E2', 96000.0, 20.0, 8000.0),
                    ('E3', 72000.0, 15.0, 6000.0),
                    ('E4', 48000.0, 10.0, 4000.0),
                    ('E5', 43200.0, 9.0, 3600.0),
                    ('F1', 38400.0, 8.0, 3200.0),
                    ('F2', 33600.0, 7.0, 2800.0),
                    ('F3', 28800.0, 6.0, 2400.0),
                    ('F4', 24000.0, 5.0, 2000.0),
                ]
                for index, (level, yearly, percentage, monthly) in enumerate(default_levels):
                    connection.execute(
                        text(
                            """
                            INSERT INTO payroll_levels (id, sort_order, level, yearly, percentage, monthly)
                            VALUES (:id, :sort_order, :level, :yearly, :percentage, :monthly)
                            """
                        ),
                        {
                            'id': str(uuid.uuid4()),
                            'sort_order': index,
                            'level': level,
                            'yearly': yearly,
                            'percentage': percentage,
                            'monthly': monthly,
                        },
                    )

        if 'expense_categories' in inspector.get_table_names():
            expense_category_count = connection.execute(text('SELECT COUNT(*) FROM expense_categories')).scalar() or 0
            if expense_category_count == 0:
                default_expense_categories = [
                    'Marketing & Advertising',
                    'Auto Expense',
                    'Bank Service Charges',
                    'Dues, Books & Subcriptions',
                    'Insurance',
                    'Internet Maintenance',
                    'Licenses & Permits',
                    'Meals & Entertainment',
                    'Merchant Account Fees',
                    'Office Supplies',
                    'Outside Services',
                    'Payroll',
                    'Payroll Tax Expense',
                    'Employee Benefits',
                    'Postage & Delivery',
                    'Printing & Reproduction',
                    'Professional Fees',
                    'Rent St marteen Warehouse',
                    'Rent / Other warehouses',
                    'Repairs & Maintenance',
                    'Telephone Expense',
                    'Travel Expense',
                    'Utilities',
                    'Miscellaneous',
                ]
                for index, name in enumerate(default_expense_categories):
                    connection.execute(
                        text(
                            """
                            INSERT INTO expense_categories (id, sort_order, name)
                            VALUES (:id, :sort_order, :name)
                            """
                        ),
                        {
                            'id': str(uuid.uuid4()),
                            'sort_order': index,
                            'name': name,
                        },
                    )

        if 'expense_entries' in inspector.get_table_names():
            expense_entry_columns = {column['name'] for column in inspector.get_columns('expense_entries')}
            if 'hardcoded_json' not in expense_entry_columns:
                connection.execute(
                    text(
                        "ALTER TABLE expense_entries ADD COLUMN hardcoded_json VARCHAR "
                        "DEFAULT '[false,false,false,false,false,false,false,false,false,false,false,false]'"
                    )
                )

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
app.include_router(payroll_levels.router)
app.include_router(expense_categories.router)
app.include_router(payroll_template.router)
app.include_router(commercial_structure.router)
