from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from .models import RepairCandidate


class RepairStatus(str, Enum):
    """
    Standardized result status for repair query orchestration.
    """
    REPAIRED = "REPAIRED"
    FAILED = "FAILED"
    NOT_REPAIRABLE = "NOT_REPAIRABLE"
    MAX_ATTEMPTS = "MAX_ATTEMPTS"


@dataclass
class RepairResult:
    """
    Every repair strategy and the engine should return this object.
    """
    success: bool
    repaired: bool
    repaired_sql: str
    repair_type: str  # e.g., "COLUMN", "TABLE", "ALIAS", "AMBIGUITY"
    candidate: Optional[RepairCandidate] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Rich orchestration fields for the final output
    final_context: Optional[object] = None
    final_validation: Optional[object] = None
    attempts: int = 0
    applied_repairs: List[RepairCandidate] = field(default_factory=list)
    status: Optional[RepairStatus] = None
    duration_ms: float = 0.0
