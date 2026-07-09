from pydantic import BaseModel


class CreateRoleRequest(BaseModel):
    role_name: str
    description: str

class UpdateRoleRequest(BaseModel):
    role_name: str
    description: str
    is_active: bool