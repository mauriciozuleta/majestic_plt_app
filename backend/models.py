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


class PayrollYearlySalary(Base):
    __tablename__ = 'payroll_yearly_salaries'

    id = Column(String, primary_key=True, index=True)
    payroll_record_id = Column(String, ForeignKey('payroll_records.id'), nullable=False, index=True)
    projection_year = Column(Integer, nullable=False)
    year_salary = Column(Float, nullable=False)
