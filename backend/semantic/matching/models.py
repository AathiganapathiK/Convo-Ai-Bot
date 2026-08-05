from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class MatchType(Enum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    SINGULAR_PLURAL = "SINGULAR_PLURAL"
    FUZZY = "FUZZY"

@dataclass(frozen=True)
class MatchResult:
    matched: bool
    value: str
    normalized_value: str
    confidence: float
    match_type: MatchType
    matched_question_tokens: List[str]
    matched_value_tokens: List[str]
    reason: str
    
    # Database mapping attributes
    dimension_id: Optional[int] = None
    business_name: Optional[str] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None

@dataclass(frozen=True)
class QuestionContext:
    raw_question: str
    normalized_question: str
    q_tokens: List[str]
    q_singulars: List[str]

@dataclass(frozen=True)
class CachedDimensionValue:
    semantic_dimension_id: int
    business_name: str
    table_name: str
    column_name: str
    value: str
    normalized_value: str
    
    # Pre-computed runtime tokens and singulars
    runtime_stored_norm: str
    runtime_stored_tokens: List[str]
    runtime_stored_singulars: List[str]
    runtime_raw_norm: str
    runtime_raw_tokens: List[str]
    runtime_raw_singulars: List[str]

@dataclass(frozen=True)
class MatchingContext:
    question_context: QuestionContext
    connection_id: str
    indexed_values: List[CachedDimensionValue]
    settings: Optional[dict] = None

@dataclass(frozen=True)
class MatchStatistics:
    exact_attempted: bool
    normalized_attempted: bool
    plural_attempted: bool
    fuzzy_attempted: bool
    winning_match: Optional[str]
    execution_time_ms: float

class BaseMatcher:
    def match(self, context: MatchingContext) -> List[MatchResult]:
        raise NotImplementedError
