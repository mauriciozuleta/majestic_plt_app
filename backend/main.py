from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .database import Base, engine
from .routers import companies, org_chart, payroll, roadmap, settings

Base.metadata.create_all(bind=engine)


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
