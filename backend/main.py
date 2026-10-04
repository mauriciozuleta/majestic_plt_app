from datetime import date
import os
import sqlite3
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

load_dotenv()

from .accounting_audit_scheduler import start_accounting_audit_scheduler
from .database import Base, engine
from .aircraft_catalog import migrate_aircraft_to_cargo
from .charter_defaults import migrate_provider_fields
from .routers import (
    accounting_audit,
    air_logistics,
    bank_accounts,
    commercial_operations,
    packer,
    commercial_structure,
    companies,
    competitiveness,
    comtrade,
    country_profile,
    currency,
    expense_categories,
    expense_providers,
    general_ledger,
    assistant,
    knowledge_base,
    market_opportunities,
    org_chart,
    payroll,
    payroll_levels,
    payroll_schedule_settings,
    payroll_template,
    price_comparison,
    product_classification,
    product_sources,
    product_overrides,
    supermarket_catalog,
    revenue_streams,
    risk_analysis,
    roadmap,
    settings,
    sim_parameters,
    product_matches,
    species_gallery,
    startup_investment,
    unit_weight_estimates,
    usa_sourcing,
    weight_research,
)

Base.metadata.create_all(bind=engine)

EXTERNAL_COUNTRY_DB = r'D:\OneDrive\0. software Lab\AI_FRESH24\db.sqlite3'


def _ensure_schema_migrations():
    inspector = inspect(engine)
    with engine.begin() as connection:
        migrate_provider_fields(connection)
        if 'logistics_aircraft' in inspector.get_table_names():
            aircraft_columns = {c['name'] for c in inspector.get_columns('logistics_aircraft')}
            # Existing aircraft remain selected. Imported/new catalogue records opt in explicitly.
            for column, definition in [('in_fleet', 'BOOLEAN NOT NULL DEFAULT 1'), ('source_aircraft_id', 'VARCHAR'), ('source_data', 'JSON')]:
                if column not in aircraft_columns:
                    connection.execute(text(f'ALTER TABLE logistics_aircraft ADD COLUMN {column} {definition}'))
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_logistics_aircraft_source ON logistics_aircraft(company_id, source_aircraft_id)'))
            migrate_aircraft_to_cargo(connection)
        if 'packer_aircraft' in inspector.get_table_names():
            if 'hidden' not in {c['name'] for c in inspector.get_columns('packer_aircraft')}:
                connection.execute(text('ALTER TABLE packer_aircraft ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0'))
        # Start-up investment moved from one flat months-array per category to
        # per-record entries (with name/description/installments) grouped by
        # category — the old table only ever held zero-filled placeholder
        # rows, so there's nothing meaningful to migrate forward.
        if 'startup_investment_entries' in inspector.get_table_names():
            connection.execute(text('DROP TABLE startup_investment_entries'))

        if 'startup_investment_plans' in inspector.get_table_names():
            plan_columns = {column['name'] for column in inspector.get_columns('startup_investment_plans')}
            if 'link_to_parent' not in plan_columns:
                connection.execute(text('ALTER TABLE startup_investment_plans ADD COLUMN link_to_parent BOOLEAN DEFAULT 0'))

        if 'portfolio_settings' in inspector.get_table_names():
            settings_columns = {column['name'] for column in inspector.get_columns('portfolio_settings')}
            if 'projection_years' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN projection_years INTEGER DEFAULT 5'))
            if 'enabled_benefits_json' not in settings_columns:
                connection.execute(text("ALTER TABLE portfolio_settings ADD COLUMN enabled_benefits_json VARCHAR DEFAULT '[]'"))
            if 'inflation_pct' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN inflation_pct FLOAT DEFAULT 0.0'))
            if 'payroll_schedule_type' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN payroll_schedule_type VARCHAR'))
            if 'payroll_schedule_monthly_day' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN payroll_schedule_monthly_day INTEGER'))
            if 'payroll_schedule_biweekly_day1' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN payroll_schedule_biweekly_day1 INTEGER'))
            if 'payroll_schedule_biweekly_day2' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN payroll_schedule_biweekly_day2 INTEGER'))
            if 'tax_obligations_schedule' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN tax_obligations_schedule VARCHAR'))
            if 'colombia_projected_cop_per_usd' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN colombia_projected_cop_per_usd FLOAT'))
            if 'colombia_smmlv_cop' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN colombia_smmlv_cop FLOAT'))
            if 'colombia_uvt_cop' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN colombia_uvt_cop FLOAT'))
            if 'real_start_date' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN real_start_date VARCHAR'))
            if 'us_payroll_state' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN us_payroll_state VARCHAR'))
            if 'audit_enabled' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN audit_enabled BOOLEAN DEFAULT 0'))
            if 'audit_interval_days' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN audit_interval_days INTEGER DEFAULT 7'))
            if 'audit_scope_company_id' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN audit_scope_company_id VARCHAR'))
            if 'audit_last_run_at' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN audit_last_run_at VARCHAR'))
            if 'phases_enabled' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN phases_enabled BOOLEAN DEFAULT 0'))
            if 'phases_count' not in settings_columns:
                connection.execute(text('ALTER TABLE portfolio_settings ADD COLUMN phases_count INTEGER'))
            if 'phases_json' not in settings_columns:
                connection.execute(text("ALTER TABLE portfolio_settings ADD COLUMN phases_json VARCHAR DEFAULT '[]'"))

        if 'companies' in inspector.get_table_names():
            company_columns = {column['name'] for column in inspector.get_columns('companies')}
            if 'country_name' not in company_columns:
                connection.execute(text('ALTER TABLE companies ADD COLUMN country_name VARCHAR'))
            if 'phase_number' not in company_columns:
                connection.execute(text('ALTER TABLE companies ADD COLUMN phase_number INTEGER'))
            if 'country_code' not in company_columns:
                connection.execute(text('ALTER TABLE companies ADD COLUMN country_code VARCHAR'))
            if 'currency_name' not in company_columns:
                connection.execute(text('ALTER TABLE companies ADD COLUMN currency_name VARCHAR'))
            if 'currency_code' not in company_columns:
                connection.execute(text('ALTER TABLE companies ADD COLUMN currency_code VARCHAR'))

            # One-time cleanup: a logo stored as a data: URL directly in this
            # column (the old behavior) is a few hundred KB to over a MB of
            # base64 text per company — moved out to a real file under
            # company_logos/ instead (see persist_logo in
            # routers/companies.py), same place any new upload goes from now
            # on. This class of storage is exactly what let a company's logo
            # silently disappear on some unrelated edit.
            legacy_logo_rows = connection.execute(text("SELECT id, logo FROM companies WHERE logo LIKE 'data:image/%'")).fetchall()
            for legacy_company_id, legacy_logo in legacy_logo_rows:
                new_logo = companies.persist_logo(legacy_company_id, legacy_logo)
                connection.execute(
                    text('UPDATE companies SET logo = :logo WHERE id = :id'),
                    {'logo': new_logo, 'id': legacy_company_id},
                )

        if 'org_chart_nodes' in inspector.get_table_names():
            node_columns = {column['name'] for column in inspector.get_columns('org_chart_nodes')}
            if 'sort_index' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN sort_index FLOAT DEFAULT 0.0'))
            if 'area' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN area VARCHAR'))
            if 'location' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN location VARCHAR'))
            if 'description' not in node_columns:
                connection.execute(text('ALTER TABLE org_chart_nodes ADD COLUMN description VARCHAR'))

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
            expense_category_columns = {column['name'] for column in inspector.get_columns('expense_categories')}
            if 'percent_of_enabled' not in expense_category_columns:
                connection.execute(text('ALTER TABLE expense_categories ADD COLUMN percent_of_enabled BOOLEAN DEFAULT 0'))
            if 'percent_of_metric' not in expense_category_columns:
                connection.execute(text('ALTER TABLE expense_categories ADD COLUMN percent_of_metric VARCHAR'))

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

        # One-time migration: expense-category applicability moves from being
        # keyed by a commercial-structure country to being keyed directly by
        # company, so it no longer silently misses a subsidiary that has no
        # commercial-structure row of its own. A country-based exclusion
        # applied to every company that owned that country row, so it
        # backfills as one row per distinct owning company. The table is
        # dropped at the end, which is also what makes this a true one-time
        # migration — the `if` above stops matching on every later startup.
        if 'expense_category_country_exclusions' in inspector.get_table_names():
            legacy_exclusions = connection.execute(
                text(
                    """
                    SELECT DISTINCT e.category_id, c.company_id
                    FROM expense_category_country_exclusions e
                    JOIN commercial_countries c ON c.id = e.country_id
                    """
                )
            ).fetchall()
            for category_id, company_id in legacy_exclusions:
                existing = connection.execute(
                    text(
                        'SELECT id FROM expense_category_company_settings WHERE category_id = :category_id AND company_id = :company_id'
                    ),
                    {'category_id': category_id, 'company_id': company_id},
                ).first()
                if existing:
                    continue
                connection.execute(
                    text(
                        """
                        INSERT INTO expense_category_company_settings (id, category_id, company_id, excluded, percent_value)
                        VALUES (:id, :category_id, :company_id, 1, NULL)
                        """
                    ),
                    {'id': str(uuid.uuid4()), 'category_id': category_id, 'company_id': company_id},
                )
            connection.execute(text('DROP TABLE expense_category_country_exclusions'))

        if 'commercial_operation_entries' in inspector.get_table_names():
            commercial_op_columns = {column['name'] for column in inspector.get_columns('commercial_operation_entries')}
            if 'entry_type' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN entry_type VARCHAR'))
            if 'client' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN client VARCHAR'))
            if 'accounting_treatment' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN accounting_treatment VARCHAR'))
            if 'is_recurring' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN is_recurring BOOLEAN DEFAULT 0'))
            if 'is_discount' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN is_discount BOOLEAN DEFAULT 0'))
            if 'settlement_date' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN settlement_date VARCHAR'))
            if 'source' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN source VARCHAR'))
            if 'schedule_key' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN schedule_key VARCHAR'))
            if 'series_id' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN series_id VARCHAR'))
            if 'reserve_account_id' not in commercial_op_columns:
                connection.execute(text('ALTER TABLE commercial_operation_entries ADD COLUMN reserve_account_id VARCHAR'))

        if 'bank_accounts' in inspector.get_table_names():
            bank_account_columns = {column['name'] for column in inspector.get_columns('bank_accounts')}
            if 'is_reserve' not in bank_account_columns:
                connection.execute(text('ALTER TABLE bank_accounts ADD COLUMN is_reserve BOOLEAN DEFAULT 0'))

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

        if 'product_sources' in inspector.get_table_names():
            product_source_columns = {column['name'] for column in inspector.get_columns('product_sources')}
            if 'currency' not in product_source_columns:
                connection.execute(text('ALTER TABLE product_sources ADD COLUMN currency VARCHAR'))
            if 'analysis_type' not in product_source_columns:
                connection.execute(text("ALTER TABLE product_sources ADD COLUMN analysis_type VARCHAR DEFAULT 'wholesaler'"))
            # analysis_type was originally 'export'/'import' (Export Analysis /
            # Import Analysis tabs); those tabs are gone, replaced by a single
            # Wholesaler/Retail label — rewrites any value saved under the old
            # names. A no-op once every row's already been converted.
            connection.execute(text("UPDATE product_sources SET analysis_type = 'wholesaler' WHERE analysis_type = 'export'"))
            connection.execute(text("UPDATE product_sources SET analysis_type = 'retail' WHERE analysis_type = 'import'"))

        if 'built_in_source_overrides' in inspector.get_table_names():
            connection.execute(text("UPDATE built_in_source_overrides SET analysis_type = 'wholesaler' WHERE analysis_type = 'export'"))
            connection.execute(text("UPDATE built_in_source_overrides SET analysis_type = 'retail' WHERE analysis_type = 'import'"))

        if 'commercial_branches' in inspector.get_table_names():
            commercial_branch_columns = {column['name'] for column in inspector.get_columns('commercial_branches')}
            branch_float_columns = [
                'latitude',
                'longitude',
                'altitude_ft',
                'fuel_cost_gl',
                'cargo_handling_cost_kg',
                'airport_fee',
                'turnaround_cost',
                'other_cost',
            ]
            for column_name in branch_float_columns:
                if column_name not in commercial_branch_columns:
                    connection.execute(text(f'ALTER TABLE commercial_branches ADD COLUMN {column_name} FLOAT'))
            if 'city' not in commercial_branch_columns:
                connection.execute(text('ALTER TABLE commercial_branches ADD COLUMN city VARCHAR'))
            if 'other_desc' not in commercial_branch_columns:
                connection.execute(text('ALTER TABLE commercial_branches ADD COLUMN other_desc VARCHAR'))

        if 'country_reference_catalog' in inspector.get_table_names():
            country_reference_columns = {column['name'] for column in inspector.get_columns('country_reference_catalog')}
            if 'trade_data_source' not in country_reference_columns:
                connection.execute(text('ALTER TABLE country_reference_catalog ADD COLUMN trade_data_source VARCHAR'))
            if 'trade_data_coverage' not in country_reference_columns:
                connection.execute(text('ALTER TABLE country_reference_catalog ADD COLUMN trade_data_coverage VARCHAR'))
            if 'trade_data_coverage_note' not in country_reference_columns:
                connection.execute(text('ALTER TABLE country_reference_catalog ADD COLUMN trade_data_coverage_note VARCHAR'))
            if 'trade_data_source_checked_at' not in country_reference_columns:
                connection.execute(text('ALTER TABLE country_reference_catalog ADD COLUMN trade_data_source_checked_at VARCHAR'))

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

        # Market Opportunities' count-vs-weight conversion (see
        # countWeightConversion.js) added conversion_note after this table
        # already existed in real databases — Base.metadata.create_all only
        # creates missing tables, never alters existing ones.
        if 'market_opportunity_comparisons' in inspector.get_table_names():
            comparison_columns = {column['name'] for column in inspector.get_columns('market_opportunity_comparisons')}
            if 'conversion_note' not in comparison_columns:
                connection.execute(text('ALTER TABLE market_opportunity_comparisons ADD COLUMN conversion_note VARCHAR'))
            if 'hs_code' not in comparison_columns:
                connection.execute(text('ALTER TABLE market_opportunity_comparisons ADD COLUMN hs_code VARCHAR'))
            if 'target_product_name' not in comparison_columns:
                connection.execute(text('ALTER TABLE market_opportunity_comparisons ADD COLUMN target_product_name VARCHAR'))
        if 'revenue_stream_routes' in inspector.get_table_names():
            route_columns = {column['name'] for column in inspector.get_columns('revenue_stream_routes')}
            for column in ('return_branch_id', 'charter_provider_id', 'aircraft_id', 'provider_name', 'aircraft_name', 'return_type'):
                if column not in route_columns:
                    connection.execute(text(f'ALTER TABLE revenue_stream_routes ADD COLUMN {column} VARCHAR'))
            if 'outbound_shipment' not in route_columns:
                connection.execute(text('ALTER TABLE revenue_stream_routes ADD COLUMN outbound_shipment VARCHAR'))
            for column in ('outbound_target_cargo_pct', 'return_target_cargo_pct', 'return_price_per_kg', 'outbound_leg_cost_pct', 'return_leg_cost_pct'):
                if column not in route_columns:
                    connection.execute(text(f'ALTER TABLE revenue_stream_routes ADD COLUMN {column} FLOAT'))


_ensure_schema_migrations()

app = FastAPI(title='MAJESTIC P.L.T. API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:5174'],
    allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
    allow_methods=['*'],
    allow_headers=['*'],
)

companies.LOGOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount('/company-logos', StaticFiles(directory=str(companies.LOGOS_DIR)), name='company-logos')

app.include_router(roadmap.router)
app.include_router(settings.router)
app.include_router(companies.router)
app.include_router(org_chart.router)
app.include_router(payroll.router)
app.include_router(payroll_levels.router)
app.include_router(expense_categories.router)
app.include_router(knowledge_base.router)
app.include_router(assistant.router)
app.include_router(product_sources.router)
app.include_router(supermarket_catalog.router)
app.include_router(product_classification.router)
app.include_router(payroll_template.router)
app.include_router(commercial_structure.router)
app.include_router(commercial_operations.router)
app.include_router(packer.router)
app.include_router(startup_investment.router)
app.include_router(sim_parameters.router)
app.include_router(revenue_streams.router)
app.include_router(general_ledger.router)
app.include_router(price_comparison.router)
app.include_router(currency.router)
app.include_router(usa_sourcing.router)
app.include_router(country_profile.router)
app.include_router(competitiveness.router)
app.include_router(weight_research.router)
app.include_router(product_overrides.router)
app.include_router(bank_accounts.router)
app.include_router(payroll_schedule_settings.router)
app.include_router(accounting_audit.router)
app.include_router(risk_analysis.router)
app.include_router(comtrade.router)
app.include_router(market_opportunities.router)
app.include_router(unit_weight_estimates.router)
app.include_router(species_gallery.router)
app.include_router(product_matches.router)
app.include_router(air_logistics.router)
app.include_router(expense_providers.router)


@app.on_event('startup')
def _on_startup():
    start_accounting_audit_scheduler()
