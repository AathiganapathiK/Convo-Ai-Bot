from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import text
from database import engine
from security.rbac_service import require_permission
from security.audit_service import audit_log, AuditAction
from admin.user_schema import CreateUserRequest, UpdateUserRequest, UserStatusRequest
from auth.password_utils import hash_password
from auth.password_validator import validate_password

router = APIRouter()

def get_company_id_by_name_or_code(connection, name_or_code: str) -> str:
    """Resolve company_id from name or code. Falls back to first active company if not found."""
    if not name_or_code:
        row = connection.execute(text("SELECT TOP 1 company_id FROM companies WHERE is_active = 1")).fetchone()
        return str(row.company_id) if row else None
        
    query = "SELECT company_id FROM companies WHERE company_name = :val OR company_code = :val"
    row = connection.execute(text(query), {"val": name_or_code}).fetchone()
    if row:
        return str(row.company_id)
        
    # Fallback to first active company
    row = connection.execute(text("SELECT TOP 1 company_id FROM companies WHERE is_active = 1")).fetchone()
    return str(row.company_id) if row else None

def sync_user_role(connection, employee_id: str, company_id: str, role_name: str):
    """Synchronize users.role_id and user_roles table with the given role name."""
    role_row = connection.execute(
        text("SELECT id FROM roles WHERE role_name = :role_name"),
        {"role_name": role_name}
    ).fetchone()
    if role_row:
        role_id = role_row.id
        # Update users table
        connection.execute(
            text("UPDATE users SET role_id = :role_id WHERE employee_id = :employee_id"),
            {"role_id": role_id, "employee_id": employee_id}
        )
        # Delete old entries from user_roles
        connection.execute(
            text("DELETE FROM user_roles WHERE employee_id = :employee_id AND company_id = :company_id"),
            {"employee_id": employee_id, "company_id": company_id}
        )
        # Insert new entry
        connection.execute(
            text("""
                INSERT INTO user_roles (company_id, employee_id, role_id)
                VALUES (:company_id, :employee_id, :role_id)
            """),
            {"company_id": company_id, "employee_id": employee_id, "role_id": role_id}
        )

@router.get("/admin/users")
def get_users(
    user=Depends(require_permission("admin:users:read"))
):
    caller_role = user.get("role", "").upper()
    if caller_role not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage users."
        )

    if caller_role == "SUPER_ADMIN":
        query = """
        SELECT
            u.id,
            u.employee_id,
            u.full_name,
            u.official_email,
            u.department,
            u.role,
            u.company,
            u.is_active,
            u.created_at,
            uda.division_code
        FROM users u
        LEFT JOIN user_division_access uda ON u.id = uda.user_id
        ORDER BY u.id
        """
        params = {}
    else:  # ADMIN
        query = """
        SELECT
            u.id,
            u.employee_id,
            u.full_name,
            u.official_email,
            u.department,
            u.role,
            u.company,
            u.is_active,
            u.created_at,
            uda.division_code
        FROM users u
        LEFT JOIN user_division_access uda ON u.id = uda.user_id
        WHERE u.company_id = :company_id 
          AND u.department = :department
          AND (u.role != 'SUPER_ADMIN' OR u.role IS NULL)
        ORDER BY u.id
        """
        params = {
            "company_id": user["company_id"],
            "department": user["department"]
        }

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        users = [dict(row._mapping) for row in result.fetchall()]

    return users


@router.post("/admin/users")
def create_user(
    request_payload: CreateUserRequest,
    request: Request,
    user=Depends(require_permission("admin:users:write"))
):
    caller_role = user.get("role", "").upper()
    if caller_role not in ("SYSTEM_ADMIN", "SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage users."
        )

    # Hierarchy validation
    if request_payload.role.upper() == "SYSTEM_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot assign SYSTEM_ADMIN role."
        )

    if caller_role == "SUPER_ADMIN":
        # Ignore company from payload for hierarchy check; locked to own company
        pass
    elif caller_role == "ADMIN":
        if request_payload.role.upper() in ("SUPER_ADMIN", "SYSTEM_ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN cannot assign SUPER_ADMIN or SYSTEM_ADMIN role."
            )
        # Lock to own department
        if request_payload.department != user["department"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN can only create users within their own department."
            )
    else: # SYSTEM_ADMIN
        # Must provide company
        if not request_payload.company:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company is required for SYSTEM_ADMIN role."
            )

    # Password Validation
    password = request_payload.password
    validate_password(password)

    check_query = """
    SELECT official_email, employee_id
    FROM users
    WHERE official_email = :official_email
       OR employee_id = :employee_id
    """

    client_ip = request.client.host if request.client else None

    with engine.begin() as connection:
        # Check for duplicates
        existing_user = connection.execute(
            text(check_query),
            {
                "official_email": request_payload.official_email,
                "employee_id": request_payload.employee_id
            }
        ).fetchone()

        if existing_user:
            existing_user = dict(existing_user._mapping)
            if existing_user["official_email"] == request_payload.official_email:
                raise HTTPException(status_code=400, detail="Official email already exists")
            if existing_user["employee_id"] == request_payload.employee_id:
                raise HTTPException(status_code=400, detail="Employee ID already exists")

        # Resolve company_id & company_name
        if caller_role == "SYSTEM_ADMIN":
            company_id = get_company_id_by_name_or_code(connection, request_payload.company)
        else:
            company_id = user["company_id"]

        if not company_id:
            raise HTTPException(status_code=400, detail="Could not resolve company_id for the user.")

        company_row = connection.execute(
            text("SELECT company_name FROM companies WHERE company_id = :cid"),
            {"cid": company_id}
        ).fetchone()
        company_name = company_row.company_name if company_row else "Unknown Company"

        hashed_password = hash_password(password)
        from repositories.user_repository import UserRepository
        from repositories.user_division_repository import UserDivisionRepository

        user_data = {
            "username":       request_payload.official_email,
            "password":       hashed_password,
            "employee_id":    request_payload.employee_id,
            "full_name":      request_payload.full_name,
            "official_email": request_payload.official_email,
            "department":     request_payload.department,
            "role":           request_payload.role,
            "company":        company_name,
            "company_id":     company_id,
        }
        # Insert user and retrieve newly created user's ID
        new_user_id = UserRepository.create_user(user_data, connection=connection)

        # Sync user roles
        sync_user_role(connection, request_payload.employee_id, company_id, request_payload.role)

        # Insert division access in the same transaction
        if new_user_id:
            UserDivisionRepository.save_division(new_user_id, request_payload.division_code, connection=connection)

            # Audit log for division change
            audit_log(
                user_id=user["employee_id"],
                action_type="DIVISION_ACCESS_CHANGED",
                resource=f"user_division_access:{request_payload.employee_id}",
                ip_address=client_ip,
                metadata={
                    "target_user_employee_id": request_payload.employee_id,
                    "previous_division": None,
                    "new_division": request_payload.division_code,
                    "changed_by": user["employee_id"]
                }
            )

        # Audit log inside transaction block
        audit_log(
            user_id=user["employee_id"],
            action_type=AuditAction.USER_CREATED,
            resource=f"user:{request_payload.employee_id}",
            ip_address=client_ip,
            metadata={
                "created_user_email": request_payload.official_email,
                "created_role": request_payload.role,
                "created_department": request_payload.department,
                "created_company": company_name,
                "assigned_company_id": str(company_id),
                "created_by": user["employee_id"],
                "created_by_role": user["role"]
            },
        )

    return {"message": "User created successfully"}


@router.put("/admin/users/{user_id}")
def update_user(
    user_id: int,
    request: UpdateUserRequest,
    req_obj: Request,
    user=Depends(require_permission("admin:users:write"))
):
    caller_role = user.get("role", "").upper()
    if caller_role not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage users."
        )

    client_ip = req_obj.client.host if req_obj.client else None

    with engine.begin() as connection:
        target_user = connection.execute(
            text("SELECT id, employee_id, role, company, company_id, department FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()

        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        target_user = dict(target_user._mapping)

        # Hierarchy validation
        if caller_role == "ADMIN":
            if target_user["role"] == "SUPER_ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN cannot manage SUPER_ADMIN accounts."
                )
            if target_user["company_id"] != user["company_id"] or target_user["department"] != user["department"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN can only manage users within their own department and company."
                )
            if request.role and request.role.upper() == "SUPER_ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN cannot assign SUPER_ADMIN role."
                )
            if request.company and request.company != user["company"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN cannot move users to another company."
                )
            if request.department and request.department != user["department"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN cannot move users to another department."
                )

        # Resolve company_id for SUPER_ADMIN if company is changing
        company_id = target_user["company_id"]
        if caller_role == "SUPER_ADMIN" and request.company and request.company != target_user["company"]:
            company_id = get_company_id_by_name_or_code(connection, request.company)

        from repositories.user_repository import UserRepository
        from repositories.user_division_repository import UserDivisionRepository

        user_data = {
            "full_name":     request.full_name if request.full_name is not None else target_user["full_name"],
            "department":    request.department if request.department is not None else target_user["department"],
            "role":          request.role if request.role is not None else target_user["role"],
            "company":       request.company if request.company is not None else target_user["company"],
            "company_id":    company_id,
            "location":      request.location,
            "mobile_number": request.mobile_number,
            "address":       request.address,
        }
        # Update user
        UserRepository.update_user(user_id, user_data, connection=connection)

        # Sync role change if role was updated
        if request.role:
            sync_user_role(connection, target_user["employee_id"], company_id, request.role)

        # Update division_code if provided in request
        if "division_code" in request.dict(exclude_unset=True):
            # Fetch previous division_code
            prev_div = UserDivisionRepository.get_division(user_id, connection=connection)

            # Update division code
            UserDivisionRepository.save_division(user_id, request.division_code, connection=connection)

            # Log audit trail if it changed
            if prev_div != request.division_code:
                audit_log(
                    user_id=user["employee_id"],
                    action_type="DIVISION_ACCESS_CHANGED",
                    resource=f"user_division_access:{target_user['employee_id']}",
                    ip_address=client_ip,
                    metadata={
                        "target_user_employee_id": target_user["employee_id"],
                        "previous_division": prev_div,
                        "new_division": request.division_code,
                        "changed_by": user["employee_id"]
                    }
                )

    audit_log(
        user_id=user["employee_id"],
        action_type=AuditAction.USER_UPDATED,
        resource=f"user:{user_id}",
        ip_address=client_ip,
        metadata={
            "updated_fields": {k: v for k, v in request.dict(exclude_unset=True).items()}
        },
    )

    return {"message": "User updated successfully"}


@router.patch("/admin/users/{user_id}/status")
def update_user_status(
    user_id: int,
    request: UserStatusRequest,
    user=Depends(require_permission("admin:users:write"))
):
    caller_role = user.get("role", "").upper()
    if caller_role not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage users."
        )

    with engine.begin() as connection:
        target_user = connection.execute(
            text("SELECT id, role, company_id, department FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()

        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        target_user = dict(target_user._mapping)

        # Hierarchy validation
        if caller_role == "ADMIN":
            if target_user["role"] == "SUPER_ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN cannot manage SUPER_ADMIN accounts."
                )
            if target_user["company_id"] != user["company_id"] or target_user["department"] != user["department"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: ADMIN can only manage users within their own department and company."
                )

        connection.execute(
            text("UPDATE users SET is_active = :is_active, updated_at = GETDATE() WHERE id = :user_id"),
            {"is_active": request.is_active, "user_id": user_id}
        )

    return {"message": "User status updated successfully"}


@router.get("/admin/users/{employee_id}/matrix")
def get_user_matrix(
    employee_id: str,
    user=Depends(require_permission("admin:users:read"))
):
    from services.access_control_service import AccessControlService
    return AccessControlService.get_user_matrix(employee_id)


@router.put("/admin/users/{employee_id}/matrix")
def update_user_matrix(
    employee_id: str,
    payload: dict,
    user=Depends(require_permission("admin:users:write"))
):
    from services.access_control_service import AccessControlService
    page_overrides = payload.get("page_overrides", payload.get("page_access", {}))
    chat_overrides = payload.get("chat_overrides", payload.get("chat_access", {}))
    data_scope = payload.get("data_scope", {})

    AccessControlService.save_user_matrix(
        employee_id=employee_id,
        page_overrides=page_overrides,
        chat_overrides=chat_overrides,
        data_scope=data_scope,
        updated_by=user.get("employee_id")
    )
    return {"message": "User access control matrix updated successfully"}