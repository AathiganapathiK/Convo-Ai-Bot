class RepairException(Exception):
    """Base exception for all SQL repair errors."""
    pass


class RepairLimitExceeded(RepairException):
    """Raised when the repair loop exceeds maximum allowed attempts."""
    pass


class NoRepairCandidate(RepairException):
    """Raised when no suitable replacement candidate is found for a repair."""
    pass


class SimilaritySearchFailed(RepairException):
    """Raised when similarity search fails to retrieve or score candidates."""
    pass
