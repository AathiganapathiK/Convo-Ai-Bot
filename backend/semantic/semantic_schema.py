from typing import Optional

from pydantic import BaseModel


class MetricRequest(BaseModel):
    metric_name: str
    business_name: str
    synonyms: Optional[str] = None
    description: Optional[str] = None
    table_name: str
    column_name: str
    aggregation_type: str
    is_active: bool = True


class DimensionRequest(BaseModel):
    dimension_name: str
    business_name: str
    synonyms: Optional[str] = None
    description: Optional[str] = None
    table_name: str
    column_name: str
    is_active: bool = True