from typing import Optional
from pydantic import BaseModel, Field


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
    location: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    parent_node_id: Optional[str] = None
    year_salary: float
    payroll_level: Optional[str] = None
    start_date: str
    projection_year: Optional[int] = None


class PayrollPositionUpdate(BaseModel):
    office_name: Optional[str] = None
    area: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    parent_node_id: Optional[str] = None
    year_salary: Optional[float] = None
    payroll_level: Optional[str] = None
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
    location: Optional[str] = None
    description: Optional[str] = None
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
    payroll_level: Optional[str] = None

    class Config:
        from_attributes = True


class PayrollLevelIn(BaseModel):
    level: str
    yearly: float
    percentage: Optional[float] = None
    monthly: Optional[float] = None


class PayrollLevelOut(PayrollLevelIn):
    id: str
    sort_order: int

    class Config:
        from_attributes = True


class PriceComparisonSnapshotOut(BaseModel):
    source: str
    products: list[dict]
    fetched_at: str


class ProductTranslationOverrideIn(BaseModel):
    product_key: str
    translation_en: str


class ProductTranslationOverrideOut(BaseModel):
    product_key: str
    translation_en: str

    class Config:
        from_attributes = True


class ExpenseCategoryOut(BaseModel):
    id: str
    sort_order: int
    name: str
    percent_of_enabled: bool = False
    percent_of_metric: Optional[str] = None

    class Config:
        from_attributes = True


class ExpenseEntryOut(BaseModel):
    category_id: str
    name: str
    sort_order: int
    projection_year: int
    months: list[float]
    hardcoded: list[bool]
    editable: bool
    excluded: bool = False
    percent_of_enabled: bool = False
    percent_of_metric: Optional[str] = None
    percent_value: Optional[float] = None


class ExpenseEntryUpdate(BaseModel):
    months: list[float]
    hardcoded: list[bool]


class ExpenseCategoryCreate(BaseModel):
    name: str


class ExpenseCategoryUpdate(BaseModel):
    name: str
    percent_of_enabled: bool = False
    percent_of_metric: Optional[str] = None


class ExpenseCategoryCompanySettingOut(BaseModel):
    category_id: str
    company_id: str
    excluded: bool
    percent_value: Optional[float] = None

    class Config:
        from_attributes = True


class ExpenseCategoryCompanySettingUpdate(BaseModel):
    category_id: str
    company_id: str
    excluded: bool = False
    percent_value: Optional[float] = None


class CommercialOperationEntryCreate(BaseModel):
    category: str
    entry_date: str
    description: Optional[str] = None
    entry_type: Optional[str] = None
    client: Optional[str] = None
    amount: float
    accounting_treatment: Optional[str] = None
    is_recurring: Optional[bool] = False
    is_discount: Optional[bool] = False
    settlement_date: Optional[str] = None
    bank_account_id: Optional[str] = None
    reference_document: Optional[str] = None
    paid_to: Optional[str] = None
    recurrence_frequency: Optional[str] = None
    recurrence_interval: Optional[int] = None
    recurrence_custom_unit: Optional[str] = None
    recurrence_until_date: Optional[str] = None
    source: Optional[str] = None
    schedule_key: Optional[str] = None
    series_id: Optional[str] = None
    reserve_account_id: Optional[str] = None


class CommercialOperationEntryOut(CommercialOperationEntryCreate):
    id: str
    company_id: str

    class Config:
        from_attributes = True


class StartupInvestmentPlanCreate(BaseModel):
    pre_operational_months: int


class StartupInvestmentPlanOut(StartupInvestmentPlanCreate):
    id: str
    company_id: str
    link_to_parent: bool = False

    class Config:
        from_attributes = True


class StartupInvestmentPlanUpdate(BaseModel):
    pre_operational_months: int


class StartupInvestmentRecordCreate(BaseModel):
    category: str
    name: str
    description: Optional[str] = None
    total_amount: float
    use_installments: bool = False
    months: Optional[list[float]] = None


class StartupInvestmentRecordOut(BaseModel):
    id: str
    company_id: str
    category: str
    name: str
    description: Optional[str] = None
    total_amount: float
    use_installments: bool
    months: list[float]
    attachment_name: Optional[str] = None

    class Config:
        from_attributes = True


class SpeciesOut(BaseModel):
    scientific_name: str
    common_name: Optional[str] = None
    gbif_key: Optional[int] = None
    gbif_rank: Optional[str] = None
    kingdom: Optional[str] = None
    family: Optional[str] = None
    resolved_from: Optional[str] = None
    resolved_term: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


# Variety Gallery's structural Tier A/Tier B separation (spec section 2): a
# PUBLIC/Gallery-facing response is built from VarietyPublicOut, which has
# NO field for image_tier_a at all — omitting it is a property of the model
# itself, not a value the endpoint remembers to leave out, so a future
# change to the public endpoint can't accidentally start returning it. Only
# VarietyAdminOut (below), used by the internal/admin path (e.g. the
# optional CV signal in matching, which needs Tier A images), carries it.
class VarietyPublicOut(BaseModel):
    id: str
    scientific_name: str
    variety_name: str
    source_country: str
    characteristics: dict
    image_tier_b: Optional[str] = None
    image_tier_b_license: Optional[str] = None
    image_tier_b_attribution: Optional[str] = None
    image_tier_b_source_url: Optional[str] = None
    confidence_status: str
    created_via: str
    created_at: str
    confirmed_at: Optional[str] = None


class VarietyAdminOut(VarietyPublicOut):
    image_tier_a: Optional[str] = None
    bootstrap_note: Optional[str] = None
