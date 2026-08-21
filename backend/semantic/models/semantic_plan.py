from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, field_validator

from semantic.temporal.models import TimeContext
from semantic.matching.models import SemanticResolutionResult


class SemanticIntent(str, Enum):
    """
    Extensible enum representing the high-level semantic intent of the query.
    """
    AGGREGATE = "AGGREGATE"
    DETAIL = "DETAIL"
    TREND = "TREND"
    COMPARISON = "COMPARISON"
    RANKED_LIST = "RANKED_LIST"
    DISTRIBUTION = "DISTRIBUTION"
    GROWTH = "GROWTH"
    DEGROWTH = "DEGROWTH"
    LOOKUP = "LOOKUP"


class SemanticQueryShape(str, Enum):
    """
    Extensible enum representing the query/display layout before generation.
    """
    SINGLE_VALUE = "SINGLE_VALUE"
    COMPARISON = "COMPARISON"
    TREND = "TREND"
    RANKED_LIST = "RANKED_LIST"
    LARGE_SUMMARY = "LARGE_SUMMARY"
    DETAIL = "DETAIL"
    DISTRIBUTION = "DISTRIBUTION"


class FilterOperator(str, Enum):
    """
    Extensible enum representing filter operators.
    """
    EQUAL = "="
    NOT_EQUAL = "!="
    IN = "IN"
    NOT_IN = "NOT IN"
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    BETWEEN = "BETWEEN"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"


class SemanticMetric(BaseModel):
    """
    Immutable representation of a resolved business metric.
    """
    model_config = ConfigDict(frozen=True)

    metric_name: str
    business_name: str
    table_name: str
    column_name: str
    aggregation_type: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    connection_id: Optional[str] = None

    @field_validator("metric_name", "business_name", "table_name", "column_name")
    @classmethod
    def fields_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Metric fields must not be empty or blank")
        return v


class SemanticDimension(BaseModel):
    """
    Immutable representation of a resolved business dimension.
    """
    model_config = ConfigDict(frozen=True)

    dimension_name: str
    business_name: str
    table_name: str
    column_name: str
    semantic_category: Optional[str] = None
    connection_id: Optional[str] = None

    @field_validator("dimension_name", "business_name", "table_name", "column_name")
    @classmethod
    def fields_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Dimension fields must not be empty or blank")
        return v


class SemanticFilter(BaseModel):
    """
    Immutable representation of a business value filter constraint.
    """
    model_config = ConfigDict(frozen=True)

    dimension_name: str
    table_name: str
    column_name: str
    operator: FilterOperator
    values: List[Any]

    @field_validator("dimension_name", "table_name", "column_name")
    @classmethod
    def fields_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Filter identifier fields must not be empty or blank")
        return v

    @field_validator("values")
    @classmethod
    def values_must_not_be_empty(cls, v: List[Any]) -> List[Any]:
        if v is None or len(v) == 0:
            raise ValueError("Filters must contain at least one value")
        return v


class SemanticTable(BaseModel):
    """
    Immutable representation of a physical schema table context.
    """
    model_config = ConfigDict(frozen=True)

    table_name: str
    business_name: Optional[str] = None
    description: Optional[str] = None
    score: Optional[float] = None
    is_bridge: bool = False

    @field_validator("table_name")
    @classmethod
    def table_name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Table name must not be empty or blank")
        return v


class SemanticJoin(BaseModel):
    """
    Immutable representation of a resolved relationship join requirement.
    """
    model_config = ConfigDict(frozen=True)

    source_table: str
    source_key: str
    target_table: str
    target_key: str
    relationship_id: Optional[str] = None
    path_length: Optional[int] = None

    @field_validator("source_table", "source_key", "target_table", "target_key")
    @classmethod
    def fields_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Join endpoints must not be empty or blank")
        return v


class SemanticPlanConfidence(BaseModel):
    """
    Authoritative representation of overall resolver pipeline confidence.
    """
    model_config = ConfigDict(frozen=True)

    status: str
    confidence: float
    reason: Optional[str] = None


class SemanticPlan(BaseModel):
    """
    Immutable and authoritative representation of resolved business meaning.
    This serves as the dialect-agnostic logical query plan before SQL generation.
    """
    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True
    )

    intent: Optional[SemanticIntent] = None
    metrics: List[SemanticMetric] = []
    dimensions: List[SemanticDimension] = []
    filters: List[SemanticFilter] = []
    temporal: Optional[TimeContext] = None
    query_shape: Optional[SemanticQueryShape] = None
    business_domain: Optional[str] = None
    primary_table: Optional[str] = None
    relevant_tables: List[SemanticTable] = []
    joins: List[SemanticJoin] = []
    ambiguity_state: Optional[SemanticResolutionResult] = None
    confidence: Optional[SemanticPlanConfidence] = None
