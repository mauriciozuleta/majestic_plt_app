from sqlalchemy import Column, Float, ForeignKey, Integer, String
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


class PortfolioSettings(Base):
    __tablename__ = 'portfolio_settings'

    id = Column(String, primary_key=True, default='singleton')
    calendar_mode = Column(String, default='real')
    projection_years = Column(Integer, default=5)


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
    start_projection_year = Column(Integer, default=0)
    growth_rate_pct = Column(Float, nullable=True)


class PayrollYearlySalary(Base):
    __tablename__ = 'payroll_yearly_salaries'

    id = Column(String, primary_key=True, index=True)
    payroll_record_id = Column(String, ForeignKey('payroll_records.id'), nullable=False, index=True)
    projection_year = Column(Integer, nullable=False)
    year_salary = Column(Float, nullable=False)
    growth_rate_pct = Column(Float, nullable=True)


class PayrollEmployee(Base):
    __tablename__ = 'payroll_employees'

    id = Column(String, primary_key=True, index=True)
    org_chart_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=False, index=True)
    employee_name = Column(String, nullable=True)
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=True)
    start_projection_year = Column(Integer, default=0)
    end_projection_year = Column(Integer, nullable=True)
    reports_to_node_id = Column(String, ForeignKey('org_chart_nodes.id'), nullable=True)
    area = Column(String, nullable=True)
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)
