class TemporalException(Exception):
    """Base exception for all time intelligence errors."""
    pass


class InvalidTimeIntent(TemporalException):
    """Raised when a time intent model fails validation rules."""
    pass


class InvalidTimeRange(TemporalException):
    """Raised when start date is after end date, or date ranges are mathematically invalid."""
    pass


class UnsupportedCalendar(TemporalException):
    """Raised when the requested calendar type is not supported by the data source."""
    pass


class StrategyResolutionError(TemporalException):
    """Raised when time strategy selection or resolution fails."""
    pass


class ContextBuildException(TemporalException):
    """Raised when context builder fails to construct TimeContext."""
    pass
