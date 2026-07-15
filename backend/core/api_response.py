from typing import Any
from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):

    code: str

    stage: Optional[str] = None

    message: str

    details: Optional[Any] = None

    retryable: bool = False


class ApiResponse(BaseModel):

    success: bool

    data: Optional[Any] = None

    error: Optional[ErrorResponse] = None

    metadata: Optional[dict] = None