from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from database import engine
from security.rbac_service import require_permission
from security.audit_service import audit_log, AuditAction
from admin.user_schema import CreateUserRequest, UpdateUserRequest, UserStatusRequest

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
            id,
            employee_id,
            full_name,
            official_email,
            department,
            role,
            company,
            is_active,
            created_at
        FROM users
        ORDER BY id
        """
        params = {}
    else:  # ADMIN
        query = """
        SELECT
            id,
            employee_id,
            full_name,
            official_email,
            department,
            role,
            company,
            is_active,
            created_at
        FROM users
        WHERE company_id = :company_id 
          AND department = :department
          AND (role != 'SUPER_ADMIN' OR role IS NULL)
        ORDER BY id
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
    request: CreateUserRequest,
    user=Depends(require_permission("admin:users:write"))
):
    caller_role = user.get("role", "").upper()
    if caller_role not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions to manage users."
        )

    # Hierarchy validation
    if caller_role == "ADMIN":
        if request.role.upper() == "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN cannot assign SUPER_ADMIN role."
            )
        if request.company != user["company"] or request.department != user["department"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: ADMIN can only create users within their own department and company."
            )

    check_query = """
    SELECT username, official_email, employee_id
    FROM users
    WHERE username = :username
       OR official_email = :official_email
       OR employee_id = :employee_id
    """

    with engine.begin() as connection:
        # Check for duplicates
        existing_user = connection.execute(
            text(check_query),
            {
                "username": request.username,
                "official_email": request.official_email,
                "employee_id": request.employee_id
            }
        ).fetchone()

        if existing_user:
            existing_user = dict(existing_user._mapping)
            if existing_user["username"] == request.username:
                raise HTTPException(status_code=400, detail="Username already exists")
            if existing_user["official_email"] == request.official_email:
                raise HTTPException(status_code=400, detail="Official email already exists")
            if existing_user["employee_id"] == request.employee_id:
                raise HTTPException(status_code=400, detail="Employee ID already exists")

        # Resolve company_id
        if caller_role == "SUPER_ADMIN":
            company_id = get_company_id_by_name_or_code(connection, request.company)
        else:
            company_id = user["company_id"]

        if not company_id:
            raise HTTPException(status_code=400, detail="Could not resolve company_id for the user.")

        # Insert user
        insert_query = """
        INSERT INTO users (
            username, password, employee_id, full_name, official_email,
            department, role, company, is_active, company_id, created_at
        ) VALUES (
            :username, '', :employee_id, :full_name, :official_email,
            :department, :role, :company, 1, :company_id, GETDATE()
        )
        """
        connection.execute(
            text(insert_query),
            {
                "username":       request.official_email,
                "employee_id":    request.employee_id,
                "full_name":      request.full_name,
                "official_email": request.official_email,
                "department":     request.department,
                "role":           request.role,
                "company":        request.company,
                "company_id":     company_id
            }
        )

        # Sync user roles
        sync_user_role(connection, request.employee_id, company_id, request.role)

    audit_log(
        user_id=user["employee_id"],
        action_type=AuditAction.USER_CREATED,
        resource=f"user:{request.employee_id}",
        metadata={
            "created_user_email": request.official_email,
            "role": request.role,
            "department": request.department,
        },
    )

    return {"message": "User created successfully"}


@router.put("/admin/users/{user_id}")
def update_user(
    user_id: int,
    request: UpdateUserRequest,
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

        # Update fields
        update_query = """
        UPDATE users
        SET
            full_name = :full_name,
            department = :department,
            role = :role,
            company = :company,
            company_id = :company_id,
            location = :location,
            mobile_number = :mobile_number,
            address = :address,
            updated_at = GETDATE()
        WHERE id = :user_id
        """
        connection.execute(
            text(update_query),
            {
                "full_name":     request.full_name if request.full_name is not None else target_user["full_name"],
                "department":    request.department if request.department is not None else target_user["department"],
                "role":          request.role if request.role is not None else target_user["role"],
                "company":       request.company if request.company is not None else target_user["company"],
                "company_id":    company_id,
                "location":      request.location,
                "mobile_number": request.mobile_number,
                "address":       request.address,
                "user_id":       user_id
            }
        )

        # Sync role change if role was updated
        if request.role:
            sync_user_role(connection, target_user["employee_id"], company_id, request.role)

    audit_log(
        user_id=user["employee_id"],
        action_type=AuditAction.USER_UPDATED,
        resource=f"user:{user_id}",
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