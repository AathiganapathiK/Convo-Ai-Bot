from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user

from security.rbac_service import require_permission

from services.role_service import RoleService

from services.permission_service import PermissionService

from admin.role_schema import (
    CreateRoleRequest,
    UpdateRoleRequest
)

router = APIRouter(
    tags=["Role Management"]
)


@router.get("/roles")
def get_roles(
    user=Depends(
        require_permission(
            "admin:users:read"
        )
    )
):

    return RoleService.get_company_roles(
        user["company_id"]
    )

@router.post("/roles")
def create_role(
    request: CreateRoleRequest,
    user=Depends(
        require_permission(
            "admin:users:write"
        )
    )
):

    RoleService.create_role(
        company_id=user["company_id"],
        role_name=request.role_name,
        description=request.description
    )

    return {
        "message":
            "Role created successfully"
    }

@router.put("/roles/{role_id}")
def update_role(
    role_id: int,
    request: UpdateRoleRequest,
    user=Depends(
        require_permission(
            "admin:users:write"
        )
    )
):

    updated = RoleService.update_role(
        role_id=role_id,
        role_name=request.role_name,
        description=request.description,
        is_active=request.is_active
    )

    if not updated:
        raise HTTPException(
            status_code=400,
            detail="Role not found or system role cannot be modified."
        )

    return {
        "message": "Role updated successfully"
    }

@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    user=Depends(
        require_permission(
            "admin:users:write"
        )
    )
):

    deleted = (
        RoleService.delete_role(
            role_id
        )
    )

    if not deleted:

        raise HTTPException(
            status_code=400,
            detail=(
                "System role "
                "cannot be deleted."
            )
        )

    return {
        "message":
            "Role deleted"
    }


@router.get("/permissions")
def get_permissions(
    user=Depends(
        require_permission(
            "admin:users:read"
        )
    )
):

    return PermissionService.get_permissions()

@router.get(
    "/roles/{role_id}/permissions"
)
def get_role_permissions(
    role_id: int,
    user=Depends(
        require_permission(
            "admin:users:read"
        )
    )
):

    return (
        PermissionService
        .get_role_permissions(
            role_id
        )
    )
