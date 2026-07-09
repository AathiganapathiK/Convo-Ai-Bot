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