from pydantic import BaseModel


class AssignRoleRequest(BaseModel):

    employee_id: str

    role_id: int