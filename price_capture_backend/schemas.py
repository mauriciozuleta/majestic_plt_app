from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class CaptureCreate(BaseModel):
    domain: str
    product_name: str
    price: str | int | float
    unit: Optional[str] = None
    country: str
    supermarket_name: str
    currency: str
    captured_at: datetime

    @field_validator('price')
    @classmethod
    def normalize_price(cls, value):
        if isinstance(value, (int, float)):
            return str(value)
        return value.strip()


class CaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    product_name: str
    price: str
    unit: Optional[str] = None
    country: str
    supermarket_name: str
    currency: str
    captured_at: datetime
    created_at: datetime
