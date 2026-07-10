from fastapi import APIRouter

from auth.auth_schema import (
    LoginRequest,
    LoginResponse
)
from services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post(
    "/login",
    response_model=LoginResponse
)
def login(
    request: LoginRequest
):
    """
    Authenticate a user using email and password.
    """

    return AuthService.authenticate_user(
        email=request.email,
        password=request.password
    )