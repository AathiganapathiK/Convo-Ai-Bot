from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from database import engine
from security.rbac_service import require_permission
from services.user_role_service import UserRoleService
from admin.user_role_schema import AssignRoleRequest

router = APIRouter(
    tags=["User Roles"]
)

def validate_user_access(caller: dict, target_employee_id: str):
    """Enforces role-based hierarchy and company/department isolation boundaries."""
    caller_role = caller.get("role", "").upper()
    if caller_role not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage roles."
        )

    with engine.connect() as connection:
        target_user = connection.execute(
            text("SELECT employee_id, role, company_id, department FROM users WHERE employee_id = :emp_id"),
            {"emp_id": target_employee_id}
        ).fetchone()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found."
        )

    target_user = dict(target_user._mapping)

    if caller_role == "ADMIN":
        if target_user["role"] == "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN cannot manage SUPER_ADMIN accounts."
            )
        if target_user["company_id"] != caller["company_id"] or target_user["department"] != caller["department"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN can only manage users within their own department and company."
            )
    return target_user


@router.post("/user-roles")
def assign_role(
    request: AssignRoleRequest,
    user=Depends(require_permission("admin:users:write"))
):
    target_user = validate_user_access(user, request.employee_id)
    
    # Do not allow admin to assign SUPER_ADMIN role
    with engine.connect() as connection:
        role_row = connection.execute(
            text("SELECT role_name FROM roles WHERE id = :role_id"),
            {"role_id": request.role_id}
        ).fetchone()
        
    if role_row and role_row.role_name == "SUPER_ADMIN" and user.get("role", "").upper() == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: ADMIN cannot assign SUPER_ADMIN role."
        )

    UserRoleService.assign_role(
        company_id=target_user["company_id"],
        employee_id=request.employee_id,
        role_id=request.role_id
    )

    return {
        "message": "Role assigned successfully"
    }


@router.delete("/user-roles/{employee_id}/{role_id}")
def remove_role(
    employee_id: str,
    role_id: int,
    user=Depends(require_permission("admin:users:write"))
):
    validate_user_access(user, employee_id)
    
    # Do not allow admin to remove a role from SUPER_ADMIN or manage SUPER_ADMIN role
    with engine.connect() as connection:
        role_row = connection.execute(
            text("SELECT role_name FROM roles WHERE id = :role_id"),
            {"role_id": role_id}
        ).fetchone()
        
    if role_row and role_row.role_name == "SUPER_ADMIN" and user.get("role", "").upper() == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: ADMIN cannot manage SUPER_ADMIN roles."
        )

    UserRoleService.remove_role(
        employee_id,
        role_id
    )

    return {
        "message": "Role removed"
    }


@router.get("/user-roles/{employee_id}")
def get_user_roles(
    employee_id: str,
    user=Depends(require_permission("admin:users:read"))
):
    target_user = validate_user_access(user, employee_id)

    return (
        UserRoleService
        .get_user_role_details(
            employee_id,
            target_user["company_id"]
        )
    )


@router.get("/user-roles/{employee_id}/names")
def get_user_role_names(
    employee_id: str,
    user=Depends(require_permission("admin:users:read"))
):
    target_user = validate_user_access(user, employee_id)

    roles = (
        UserRoleService
        .get_user_role_details(
            employee_id,
            target_user["company_id"]
        )
    )

    return [
        role["role_name"]
        for role in roles
    ]