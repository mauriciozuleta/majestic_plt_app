from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, UniqueConstraint
from .database import Base


class Company(Base):
    __tablename__ = 'companies'

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    logo = Column(String, nullable=True)
    company_type = Column(String, nullable=False)
    company_dependency = Column(String, nullable=False)
    parent_company_id = Column(String, nullable=True)
    accent_from = Column(String, nullable=False)
    accent_to = Column(String, nullable=False)
    country_name = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    currency_name = Column(String, nullable=True)
    currency_code = Column(String, nullable=True)


class PortfolioSettings(Base):
    __tablename__ = 'portfolio_settings'

    id = Column(String, primary_key=True, default='singleton')
    calendar_mode = Column(String, default='real')
    projection_years = Column(Integer, default=5)
    enabled_benefits_json = Column(String, default='[]')
    inflation_pct = Column(Float, default=0.0)
    payroll_schedule_type = Column(String, nullable=True)
    payroll_schedule_monthly_day = Column(Integer, nullable=True)
    payroll_schedule_biweekly_day1 = Column(Integer, nullable=True)
    payroll_schedule_biweekly_day2 = Column(Integer, nullable=True)
    tax_obligations_schedule = Column(String, nullable=True)
    colombia_projected_cop_per_usd = Column(Float, nullable=True)
    colombia_smmlv_cop = Column(Float, nullable=True)
    colombia_uvt_cop = Column(Float, nullable=True)


class RoadmapTask(Base):
    __tablename__ = 'roadmap_tasks'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
    progress = Column(Integer, default=0)
    dependencies = Column(String, default='')
    responsible = Column(String, default='')
    parent_task_id = Column(String, nullable=True)
    sort_index = Column(Float, default=0.0)
    linked_company_id = Column(String, nullable=True)


class OrgChartNode(Base):
    __tablename__ = 'org_chart_nodes'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    office_name = Column(String, nullable=False)
    employee_name = Column(String, nullable=True)
    area = Column(String, nullable=True)
    location = Column(String, nullable=True)
    description = Column(String, nullable=True)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    sort_index = Column(Float, default=0.0)


class CommercialRegion(Base):
    __tablename__ = 'commercial_regions'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    manager_name = Column(String, nullable=True)
    user_name = Column(String, nullable=True)


class CommercialCountry(Base):
    __tablename__ = 'commercial_countries'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    region_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    country_code = Column(String, nullable=True, index=True)
    currency = Column(String, nullable=True)
    currency_code = Column(String, nullable=True)
    manager_name = Column(String, nullable=True)
    user_name = Column(String, nullable=True)


class CountryReferenceCatalog(Base):
    __tablename__ = 'country_reference_catalog'

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    country_code = Column(String, nullable=False, unique=True, index=True)
    currency = Column(String, nullable=False)
    currency_code = Column(String, nullable=False)
    region = Column(String, nullable=False, index=True)


class CommercialBranch(Base):
    __tablename__ = 'commercial_branches'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    country_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    manager_name = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    airport = Column(String, nullable=True)
    active = Column(String, default='active')
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude_ft = Column(Float, nullable=True)
    fuel_cost_gl = Column(Float, nullable=True)
    cargo_handling_cost_kg = Column(Float, nullable=True)
    airport_fee = Column(Float, nullable=True)
    turnaround_cost = Column(Float, nullable=True)
    other_desc = Column(String, nullable=True)
    other_cost = Column(Float, nullable=True)


class RevenueStream(Base):
    __tablename__ = 'revenue_streams'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    revenue_type = Column(String, nullable=False)  # 'main' | 'secondary'
    name = Column(String, nullable=False)


class GeneralLedgerAccount(Base):
    __tablename__ = 'general_ledger_accounts'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    account_type = Column(String, nullable=False)  # asset | liability | equity | revenue | contra_revenue | expense
    normal_balance = Column(String, nullable=False)  # debit | credit


class JournalEntry(Base):
    __tablename__ = 'journal_entries'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    entry_date = Column(String, nullable=False, index=True)
    memo = Column(String, nullable=True)
    source_type = Column(String, nullable=True)  # 'commercial_operation_entry'
    source_id = Column(String, nullable=True, index=True)


class JournalLine(Base):
    __tablename__ = 'journal_lines'

    id = Column(String, primary_key=True, index=True)
    journal_entry_id = Column(String, ForeignKey('journal_entries.id'), nullable=False, index=True)
    account_id = Column(String, ForeignKey('general_ledger_accounts.id'), nullable=False, index=True)
    debit = Column(Float, nullable=False, default=0.0)
    credit = Column(Float, nullable=False, default=0.0)


class OrgChartEdge(Base):
    __tablename__ = 'org_chart_edges'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    source_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=False)
    target_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=False)


class PayrollRecord(Base):
    __tablename__ = 'payroll_records'

    id = Column(String, primary_key=True, index=True)
    org_chart_node_id = Column(String, ForeignKey('org_chart_nodes.id'), unique=True, nullable=False)
    year_salary = Column(Float, nullable=False)
    start_date = Column(String, nullable=False)
    start_projection_year = Column(Integer, default=1)
    growth_rate_pct = Column(Float, nullable=True)


class PayrollYearlySalary(Base):
    __tablename__ = 'payroll_yearly_salaries'

    id = Column(String, primary_key=True, index=True)
    payroll_record_id = Column(String, ForeignKey('payroll_records.id'), nullable=False, index=True)
    projection_year = Column(Integer, nullable=False)
    year_salary = Column(Float, nullable=False)
    growth_rate_pct = Column(Float, nullable=True)
    payroll_level = Column(String, nullable=True)


class PayrollLevel(Base):
    __tablename__ = 'payroll_levels'

    id = Column(String, primary_key=True, index=True)
    sort_order = Column(Integer, default=0)
    level = Column(String, nullable=False)
    yearly = Column(Float, nullable=False)
    percentage = Column(Float, nullable=True)
    monthly = Column(Float, nullable=True)


class ExpenseCategory(Base):
    __tablename__ = 'expense_categories'

    id = Column(String, primary_key=True, index=True)
    sort_order = Column(Integer, default=0)
    name = Column(String, nullable=False)


class ExpenseEntry(Base):
    __tablename__ = 'expense_entries'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    category_id = Column(String, ForeignKey('expense_categories.id'), nullable=False, index=True)
    projection_year = Column(Integer, nullable=False)
    months_json = Column(String, nullable=False, default='[0,0,0,0,0,0,0,0,0,0,0,0]')
    hardcoded_json = Column(String, nullable=False, default='[false,false,false,false,false,false,false,false,false,false,false,false]')


class ExpenseCategoryCountryExclusion(Base):
    """An explicit opt-out: this expense category does NOT apply to this
    country. Absence of a row means "applies" — so a newly added category or
    country is applicable everywhere by default with no backfill needed."""
    __tablename__ = 'expense_category_country_exclusions'
    __table_args__ = (UniqueConstraint('category_id', 'country_id', name='uq_expense_category_country'),)

    id = Column(String, primary_key=True, index=True)
    category_id = Column(String, ForeignKey('expense_categories.id'), nullable=False, index=True)
    country_id = Column(String, ForeignKey('commercial_countries.id'), nullable=False, index=True)


class StartupInvestmentPlan(Base):
    __tablename__ = 'startup_investment_plans'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, unique=True, nullable=False, index=True)
    pre_operational_months = Column(Integer, nullable=False)


class StartupInvestmentRecord(Base):
    __tablename__ = 'startup_investment_records'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    total_amount = Column(Float, nullable=False)
    use_installments = Column(Boolean, default=False)
    months_json = Column(String, nullable=False, default='[]')
    attachment_name = Column(String, nullable=True)


class CommercialOperationEntry(Base):
    __tablename__ = 'commercial_operation_entries'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    category = Column(String, nullable=False)  # 'revenue' | 'cos' | 'expenses'
    entry_date = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    entry_type = Column(String, nullable=True)  # revenue entries: a free-text type
    client = Column(String, nullable=True)  # revenue entries: the client name
    amount = Column(Float, nullable=False)
    accounting_treatment = Column(String, nullable=True)  # e.g. 'earned', 'accrued', 'deferred', 'capex' — meaning is category-specific
    is_recurring = Column(Boolean, nullable=True, default=False)  # revenue only: subscriptions/memberships
    is_discount = Column(Boolean, nullable=True, default=False)  # revenue only: negative revenue adjustment
    settlement_date = Column(String, nullable=True)  # when the cash is actually paid/received, if different from entry_date


class SimParameter(Base):
    """Flags a commercial-operations entry as a lever the (future) simulation
    agent is allowed to manipulate. Just a link table for now — no
    simulation logic reads this yet."""

    __tablename__ = 'sim_parameters'

    id = Column(String, primary_key=True, index=True)
    company_id = Column(String, index=True, nullable=False)
    entry_id = Column(String, index=True, nullable=False, unique=True)


class PayrollEmployee(Base):
    __tablename__ = 'payroll_employees'

    id = Column(String, primary_key=True, index=True)
    org_chart_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=False, index=True)
    employee_name = Column(String, nullable=True)
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=True)
    start_projection_year = Column(Integer, default=1)
    end_projection_year = Column(Integer, nullable=True)
    reports_to_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=True)
    area = Column(String, nullable=True)
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)


class PriceComparisonSnapshot(Base):
    """Last successfully fetched product list for one Colombia price source,
    so the comparison table has something to show on page load without
    forcing the user to click Update every time (the fetch itself is still
    only ever triggered by Update — this just persists its last result)."""
    __tablename__ = 'price_comparison_snapshots'

    source = Column(String, primary_key=True)
    data_json = Column(String, nullable=False)
    fetched_at = Column(String, nullable=False)


class ProductTranslationOverride(Base):
    """User-submitted English translation for a Colombia price-comparison
    product, keyed by the same normalized id the price-source parsers use.
    Supplements — never replaces — the static dictionary in
    src/.../productTranslations.js; an entry here wins when both exist."""
    __tablename__ = 'product_translation_overrides'

    product_key = Column(String, primary_key=True, index=True)
    translation_en = Column(String, nullable=False)


class ProductWeightResearch(Base):
    """AI-researched net weight (in kg) for a product/pack whose price the
    scrapers can't convert to $/kg from the source data alone (e.g. a USA
    produce carton whose weight isn't captured, or a Colombia count-based
    package like "CAJA (10 per package)"). Global, not per-company — a
    carton's standard weight is a fact about the pack, not about which
    company is looking at it, so one research result is reusable everywhere.
    Keyed by a stable signature (see backend/weight_research/signatures.py)
    rather than the raw product name, since the same pack type recurs across
    many differently-sized/labeled rows (all of a crop's carton sizes share
    one real carton weight)."""
    __tablename__ = 'product_weight_research'

    signature = Column(String, primary_key=True, index=True)
    description = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=True)
    confidence = Column(String, nullable=True)
    note = Column(String, nullable=True)
    sources_json = Column(String, nullable=False, default='[]')
    researched_at = Column(String, nullable=False)


class ProductCustomOverride(Base):
    """A user-entered correction for one exact priced row (a specific
    product at a specific source/size — finer-grained than
    ProductWeightResearch's pack-level signature, since a price correction
    is naturally per row, not shared across every size grade of a pack).
    Either field alone is valid: a price-only override keeps using
    whatever weight was already resolved (official or researched); a
    weight-only override keeps the source's own price. Global, not
    per-company, matching ProductWeightResearch."""
    __tablename__ = 'product_custom_overrides'

    signature = Column(String, primary_key=True, index=True)
    custom_price = Column(Float, nullable=True)
    custom_weight_kg = Column(Float, nullable=True)
    updated_at = Column(String, nullable=False)
