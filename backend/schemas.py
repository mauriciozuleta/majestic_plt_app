from typing import Optional
from pydantic import BaseModel


class RoadmapTaskBase(BaseModel):
    name: str
    start: str
    end: str
    progress: int = 0
    dependencies: str = ''
    responsible: str = ''
    parent_task_id: Optional[str] = None
    sort_index: float = 0.0
    linked_company_id: Optional[str] = None


class RoadmapTaskCreate(RoadmapTaskBase):
    pass


class RoadmapTaskUpdate(BaseModel):
    name: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    progress: Optional[int] = None
    dependencies: Optional[str] = None
    responsible: Optional[str] = None
    parent_task_id: Optional[str] = None
    sort_index: Optional[float] = None
    linked_company_id: Optional[str] = None


class RoadmapTaskOut(RoadmapTaskBase):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class OrgChartNodeBase(BaseModel):
    office_name: str
    employee_name: Optional[str] = None
    area: Optional[str] = None
    position_x: int = 0
    position_y: int = 0
    sort_index: float = 0.0


class OrgChartNodeCreate(OrgChartNodeBase):
    pass


class OrgChartNodeUpdate(BaseModel):
    office_name: Optional[str] = None
    employee_name: Optional[str] = None
    area: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    sort_index: Optional[float] = None


class OrgChartNodeOut(OrgChartNodeBase):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class OrgChartEdgeCreate(BaseModel):
    source_node_id: str
    target_node_id: str


class OrgChartEdgeOut(OrgChartEdgeCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class PayrollPositionCreate(BaseModel):
    office_name: str
    employee_name: Optional[str] = None
    area: Optional[str] = None
    parent_node_id: Optional[str] = None
    year_salary: float
    start_date: str
    projection_year: Optional[int] = None


class PayrollPositionUpdate(BaseModel):
    office_name: Optional[str] = None
    area: Optional[str] = None
    parent_node_id: Optional[str] = None
    year_salary: Optional[float] = None
    projection_year: Optional[int] = None
    sort_index: Optional[float] = None


class PayrollGrowthApply(BaseModel):
    rate_pct: float


class PayrollEmployeeBase(BaseModel):
    employee_name: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    reports_to_node_id: Optional[str] = None
    area: Optional[str] = None


class PayrollEmployeeCreate(PayrollEmployeeBase):
    pass


class PayrollEmployeeUpdate(BaseModel):
    employee_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_projection_year: Optional[int] = None
    end_projection_year: Optional[int] = None
    reports_to_node_id: Optional[str] = None
    area: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None


class PayrollEmployeeOut(PayrollEmployeeBase):
    id: str
    org_chart_node_id: str
    start_projection_year: int
    end_projection_year: Optional[int] = None

    class Config:
        from_attributes = True


class PayrollRowOut(BaseModel):
    node_id: str
    office_name: str
    employee_name: Optional[str]
    area: Optional[str]
    parent_node_id: Optional[str]
    level: int
    sort_index: float
    projection_year: int
    year_salary: float
    monthly_salary: float
    start_date: str
    headcount: int = 1
    employees: list[PayrollEmployeeOut] = []
    linked_company_id: Optional[str] = None
    growth_rate_pct: Optional[float] = None

    class Config:
        from_attributes = True
