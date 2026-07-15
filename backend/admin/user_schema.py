from pydantic import BaseModel
from typing import Optional


class CreateUserRequest(BaseModel):

    #username: str

    password: str

    employee_id: str

    full_name: str

    official_email: str

    department: str

    role: str

    company: str

class UpdateUserRequest(BaseModel):

    full_name: Optional[str] = None

    department: Optional[str] = None

    role: Optional[str] = None

    company: Optional[str] = None

    location: Optional[str] = None

    mobile_number: Optional[str] = None

    address: Optional[str] = None

class UserStatusRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    temporary_password: str


class ChangePasswordRequest(BaseModel):
    employee_id: str
    new_password: str