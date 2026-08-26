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


class AnalysisMode(str, Enum):
    """
    The kind of analysis a question asks for.

    Added in Gate 1. This is the authoritative mode going forward; SemanticIntent
    and SemanticQueryShape are retained because the resolver and prompt builder
    still read them, and are mapped onto this enum by MODE_FROM_INTENT below.
    DIAGNOSTIC and PRESCRIPTIVE are recognised from Gate 4 but not executed until
    Gates 8 and 9 - a plan carrying them is not yet a plan that can be answered.
    """
    DESCRIPTIVE = "DESCRIPTIVE"
    COMPARISON = "COMPARISON"
    TREND = "TREND"
    RANKING = "RANKING"
    DIAGNOSTIC = "DIAGNOSTIC"
    PRESCRIPTIVE = "PRESCRIPTIVE"


class OutputFormat(str, Enum):
    """
    Extensible enum representing the shape of the assembled response.
    """
    KPI = "kpi"
    TABLE = "table"
    CHART = "chart"
    NARRATIVE = "narrative"


class RankDirection(str, Enum):
    """
    Extensible enum representing ranking order.
    """
    ASC = "ASC"
    DESC = "DESC"


class RankMeasure(str, Enum):
    """
    What a ranking is ordered by.

    Without this, "top 5 products whose sales are reducing" is ambiguous: ASC on
    the metric value and ASC on the change in that value are different questions
    with different answers.
    """
    ABSOLUTE = "ABSOLUTE"
    CHANGE = "CHANGE"
    CHANGE_PCT = "CHANGE_PCT"


class BenchmarkType(str, Enum):
    """
    A non-temporal comparison basis.

    TimeContext.comparison expresses period-over-period only, so "versus target",
    "versus the regional average", "versus forecast" and "versus plan" had no
    representation before Gate 1.
    """
    TARGET = "TARGET"
    PEER_AVERAGE = "PEER_AVERAGE"
    FORECAST = "FORECAST"
    PLAN = "PLAN"


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


class SemanticRanking(BaseModel):
    """
    Immutable representation of a ranking request.
    """
    model_config = ConfigDict(frozen=True)

    top_n: Optional[int] = None
    direction: Optional[RankDirection] = None
    measure: Optional[RankMeasure] = None

    @field_validator("top_n")
    @classmethod
    def top_n_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("top_n must be a positive integer")
        return v


class SemanticBenchmark(BaseModel):
    """
    Immutable representation of a non-temporal comparison basis.
    """
    model_config = ConfigDict(frozen=True)

    benchmark_type: BenchmarkType
    reference: Optional[str] = None


class SemanticDiagnostic(BaseModel):
    """
    Immutable representation of a root-cause decomposition request.

    Populated from Gate 4 (recognition) and executed from Gate 8. `steps` is
    constrained by the bounded investigation policy - the Investigator selects
    from a fixed menu rather than composing arbitrary analysis.
    """
    model_config = ConfigDict(frozen=True)

    candidate_dimensions: List[str] = []
    steps: List[str] = []


class SemanticOutput(BaseModel):
    """
    Immutable representation of the intended response shape.
    """
    model_config = ConfigDict(frozen=True)

    output_format: Optional[OutputFormat] = None
    chart_type: Optional[str] = None


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

    # --- Gate 1 additions ---------------------------------------------------
    # All optional so existing construction sites and readers are unaffected.
    # Populated progressively: mode/output/ranking from Gate 4, benchmark from
    # Gate 4, diagnostic from Gate 8. assumptions_made is written by any stage
    # that fills a default on the user's behalf.
    mode: Optional[AnalysisMode] = None
    output: Optional[SemanticOutput] = None
    ranking: Optional[SemanticRanking] = None
    benchmark: Optional[SemanticBenchmark] = None
    diagnostic: Optional[SemanticDiagnostic] = None
    assumptions_made: List[str] = []

    @property
    def effective_mode(self) -> Optional[AnalysisMode]:
        """
        The plan's mode, falling back to a translation of the legacy intent enum
        when mode has not been set explicitly.

        Lets downstream code read one field during the period where both the old
        and new taxonomies are live, without every caller repeating the mapping.
        """
        if self.mode is not None:
            return self.mode
        if self.intent is not None:
            return MODE_FROM_INTENT.get(self.intent)
        return None


# ---------------------------------------------------------------------------
# Legacy taxonomy translation (Gate 1, step 5)
# ---------------------------------------------------------------------------
# SemanticIntent and SemanticQueryShape predate AnalysisMode and are still read
# by the resolver and prompt builder, so they are mapped rather than removed.
# Retiring them belongs to Gate 7, when the prompt builder module is split.
# (Avoid writing file extensions in this module: the no-hardcoding guard in
#  test_semantic_plan treats a dot as a word boundary and reads them as the
#  business terms it exists to keep out.)
#
# Note the deliberate collapse: AGGREGATE, DETAIL, DISTRIBUTION and LOOKUP all
# become DESCRIPTIVE. They differ in output shape, not in kind of analysis, and
# output shape is now carried by SemanticPlan.output. GROWTH and DEGROWTH become
# COMPARISON because both are a period measured against another period; the
# direction they imply belongs on SemanticRanking.measure, not on the mode.

MODE_FROM_INTENT: dict = {
    SemanticIntent.AGGREGATE: AnalysisMode.DESCRIPTIVE,
    SemanticIntent.DETAIL: AnalysisMode.DESCRIPTIVE,
    SemanticIntent.DISTRIBUTION: AnalysisMode.DESCRIPTIVE,
    SemanticIntent.LOOKUP: AnalysisMode.DESCRIPTIVE,
    SemanticIntent.TREND: AnalysisMode.TREND,
    SemanticIntent.COMPARISON: AnalysisMode.COMPARISON,
    SemanticIntent.GROWTH: AnalysisMode.COMPARISON,
    SemanticIntent.DEGROWTH: AnalysisMode.COMPARISON,
    SemanticIntent.RANKED_LIST: AnalysisMode.RANKING,
}

MODE_FROM_QUERY_SHAPE: dict = {
    SemanticQueryShape.SINGLE_VALUE: AnalysisMode.DESCRIPTIVE,
    SemanticQueryShape.DETAIL: AnalysisMode.DESCRIPTIVE,
    SemanticQueryShape.DISTRIBUTION: AnalysisMode.DESCRIPTIVE,
    SemanticQueryShape.LARGE_SUMMARY: AnalysisMode.DESCRIPTIVE,
    SemanticQueryShape.TREND: AnalysisMode.TREND,
    SemanticQueryShape.COMPARISON: AnalysisMode.COMPARISON,
    SemanticQueryShape.RANKED_LIST: AnalysisMode.RANKING,
}

# Default response shape per mode. Gate 4 response assembly reads plan.output
# when set and falls back here, so mode drives presentation rather than the
# returned row count.
DEFAULT_OUTPUT_FORMAT: dict = {
    AnalysisMode.DESCRIPTIVE: OutputFormat.KPI,
    AnalysisMode.COMPARISON: OutputFormat.TABLE,
    AnalysisMode.TREND: OutputFormat.CHART,
    AnalysisMode.RANKING: OutputFormat.TABLE,
    AnalysisMode.DIAGNOSTIC: OutputFormat.NARRATIVE,
    AnalysisMode.PRESCRIPTIVE: OutputFormat.NARRATIVE,
}

# DIAGNOSTIC and PRESCRIPTIVE have no legacy equivalent by design - the old
# taxonomy had no concept of either, which is why the system could not
# distinguish "why did sales fall" from "show me sales".
EXECUTABLE_MODES: frozenset = frozenset({
    AnalysisMode.DESCRIPTIVE,
    AnalysisMode.COMPARISON,
    AnalysisMode.TREND,
    AnalysisMode.RANKING,
})
