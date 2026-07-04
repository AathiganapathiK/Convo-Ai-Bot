from pydantic import BaseModel


class CreateRoleRequest(BaseModel):
    role_name: str
    description: str