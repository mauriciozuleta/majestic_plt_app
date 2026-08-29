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
    employee_name: Optional[str] = None
    area: Optional[str] = None
    parent_node_id: Optional[str] = None
    year_salary: Optional[float] = None
    start_date: Optional[str] = None
    projection_year: Optional[int] = None


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
    linked_company_id: Optional[str] = None

    class Config:
        from_attributes = True
