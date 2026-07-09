from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from core.api_response import ErrorResponse
from core.error_codes import ErrorCode
from core.exceptions import DatasourceLifecycleException


async def datasource_exception_handler(
    request: Request,
    exc: Exception
) -> Response:

    if not isinstance(exc, DatasourceLifecycleException):
        return await generic_exception_handler(request, exc)

    lifecycle_exception = exc

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": ErrorResponse(
                code=lifecycle_exception.code.value,
                stage=lifecycle_exception.stage,
                message=lifecycle_exception.message,
                details=lifecycle_exception.details,
                retryable=lifecycle_exception.retryable
            ).model_dump()
        }
    )

async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> Response:

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": ErrorResponse(
                code=ErrorCode.UNKNOWN_ERROR.value,
                message=str(exc),
                retryable=False
            ).model_dump()
        }
    )