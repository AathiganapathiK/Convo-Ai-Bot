"""
auth/rbac.py

Role-based access control (RBAC) FastAPI dependencies.
Roles are loaded from the SQL Server users table by get_current_user().
No hardcoded role strings beyond the allowed-role lists defined here.
"""

import logging
from fastapi import Depends, HTTPException, status
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Canonical role identifiers — must match values stored in users.role column.
ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_ADMIN       = "ADMIN"
ROLE_ANALYST     = "ANALYST"


def require_roles(allowed_roles: list[str]):
    """
    Returns a FastAPI dependency that enforces membership in allowed_roles.
    The role is sourced from the DB-backed get_current_user() result.
    """
    def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "")
        if user_role not in allowed_roles:
            logger.warning(
                "Access denied: user '%s' has role '%s', required one of %s.",
                user.get("official_email"),
                user_role,
                allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: insufficient role.",
            )
        return user
    return role_checker


def admin_required(user: dict = Depends(get_current_user)) -> dict:
    """Allow SUPER_ADMIN and ADMIN only."""
    return require_roles([ROLE_SUPER_ADMIN, ROLE_ADMIN])(user)


def analyst_required(user: dict = Depends(get_current_user)) -> dict:
    """Allow SUPER_ADMIN, ADMIN, and ANALYST."""
    return require_roles([ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ANALYST])(user)

def super_admin_required(user: dict = Depends(get_current_user)) -> dict:
    """Allow SUPER_ADMIN ONLY."""
    return require_roles([ROLE_SUPER_ADMIN])(user)
