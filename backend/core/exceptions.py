from core.error_codes import ErrorCode


class DatasourceLifecycleException(Exception):

    def __init__(
        self,
        code: ErrorCode,
        stage: str,
        message: str,
        details=None,
        retryable: bool = False
    ):

        self.code = code
        self.stage = stage
        self.message = message
        self.details = details
        self.retryable = retryable

        super().__init__(message)

class EnterpriseException(Exception):
    """
    Base class for all business exceptions in the platform.
    """

    def __init__(
        self,
        error_code: str,
        category: str,
        title: str,
        message: str,
        suggestion: str = "",
        details: dict | None = None
    ):
        super().__init__(message)

        self.error_code = error_code
        self.category = category
        self.title = title
        self.message = message
        self.suggestion = suggestion
        self.details = details or {}

    def to_dict(self):

        return {

            "success": False,

            "error": {

                "code": self.error_code,

                "category": self.category,

                "title": self.title,

                "message": self.message,

                "suggestion": self.suggestion,

                "details": self.details

            }

        }

class SemanticRetrievalException(EnterpriseException):

    def __init__(self, message=None, details=None):
        msg = message or (
            "I couldn't identify the business metrics, "
            "dimensions or values in your question."
        )
        super().__init__(

            error_code=ErrorCode.SEMANTIC_NOT_RECOGNIZED,

            category="SEMANTIC",

            title="Business Terms Not Recognized",

            message=msg,

            suggestion=(
                "Try using known business terms such as Sales, "
                "Revenue, Product, Region, Customer or Employee."
            ),

            details=details

        )



class AmbiguityException(EnterpriseException):

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            error_code="AMBIGUITY_DETECTED",
            category="SEMANTIC",
            title="Clarification Required",
            message=message,
            suggestion="Please clarify by selecting one of the options.",
            details=details
        )

    def to_dict(self):
        dct = super().to_dict()
        dct["action"] = "CLARIFICATION_REQUIRED"
        return dct


class CLSException(EnterpriseException):

    def __init__(self, message: str, details: dict | None = None):

        super().__init__(

            error_code=ErrorCode.CLS_BLOCKED,

            category="SECURITY",

            title="Access Denied",

            message=message,

            suggestion="Inform the user they do not have permission to access the requested data.",

            details=details

        )


class SQLValidationException(EnterpriseException):

    def __init__(self, message: str, details: dict | None = None):

        super().__init__(

            error_code=ErrorCode.SQL_INVALID_QUERY,

            category="SQL",

            title="Invalid SQL Query",

            message=message,

            suggestion="Modify the question or contact an administrator if the issue persists.",

            details=details

        )


class InternalSystemException(EnterpriseException):

    def __init__(self, message: str, details: dict | None = None):

        super().__init__(

            error_code=ErrorCode.INTERNAL_ERROR,

            category="SYSTEM",

            title="Internal Server Error",

            message=message,

            suggestion="Please try again later or contact the administrator.",

            details=details

        )

