CONNECTION_FAILED = "CONNECTION_FAILED"

SCHEMA_SYNC_FAILED = "SCHEMA_SYNC_FAILED"

RELATIONSHIP_DISCOVERY_FAILED = "RELATIONSHIP_DISCOVERY_FAILED"

SEMANTIC_DISCOVERY_FAILED = "SEMANTIC_DISCOVERY_FAILED"

DRIFT_DETECTION_FAILED = "DRIFT_DETECTION_FAILED"

UNKNOWN_ERROR = "UNKNOWN_ERROR"


from enum import Enum


class ErrorCode(str, Enum):

    CONNECTION_FAILED = "CONNECTION_FAILED"

    ENABLE_FAILED = "ENABLE_FAILED"

    SCHEMA_SYNC_FAILED = "SCHEMA_SYNC_FAILED"

    RELATIONSHIP_DISCOVERY_FAILED = "RELATIONSHIP_DISCOVERY_FAILED"

    SEMANTIC_DISCOVERY_FAILED = "SEMANTIC_DISCOVERY_FAILED"

    DRIFT_DETECTION_FAILED = "DRIFT_DETECTION_FAILED"

    VALIDATION_FAILED = "VALIDATION_FAILED"

    PERMISSION_DENIED = "PERMISSION_DENIED"

    UNKNOWN_ERROR = "UNKNOWN_ERROR"


    """
    Enterprise Error Codes
    """

    # --------------------------------------------------
    # Semantic Layer
    # --------------------------------------------------

    SEMANTIC_NOT_RECOGNIZED = "SEMANTIC_001"
    SEMANTIC_VALUE_NOT_FOUND = "SEMANTIC_002"

    # --------------------------------------------------
    # SQL Validation
    # --------------------------------------------------

    SQL_INVALID_TABLE = "SQL_001"
    SQL_INVALID_COLUMN = "SQL_002"
    SQL_INVALID_JOIN = "SQL_003"
    SQL_INVALID_QUERY = "SQL_004"
    SQL_GENERATION_FAILED = "SQL_005"

    # --------------------------------------------------
    # Data
    # --------------------------------------------------

    DATA_NOT_FOUND = "DATA_001"

    # --------------------------------------------------
    # Security
    # --------------------------------------------------

    CLS_BLOCKED = "SECURITY_001"
    RLS_FILTERED = "SECURITY_002"
    SQL_SECURITY_BLOCKED = "SECURITY_003"

    # --------------------------------------------------
    # Database
    # --------------------------------------------------

    DATABASE_CONNECTION_FAILED = "DATABASE_001"

    # --------------------------------------------------
    # AI / LLM
    # --------------------------------------------------

    LLM_PROVIDER_ERROR = "LLM_001"

    # --------------------------------------------------
    # System
    # --------------------------------------------------

    INTERNAL_ERROR = "SYSTEM_001"