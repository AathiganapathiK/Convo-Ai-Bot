"""
security/rbac_service.py

Database-driven RBAC with permission-based authorization.

Loads permissions from the roles / permissions / role_permissions tables.
Provides the `require_permission(permission_name)` FastAPI dependency.

No hardcoded role checks — all authorization decisions are driven by the
permission assignments stored in the database.
"""

import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from sqlalchemy import text

from database import engine
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission cache (invalidated on role/permission changes)
# ---------------------------------------------------------------------------

_permission_cache: dict[str, set[str]] = {}
_cache_loaded: bool = False


def _load_permissions() -> dict[str, set[str]]:
    """
    Load all role → permissions mappings from the database.
    Returns {role_name: {permission_name, ...}, ...}
    """
    query = """
    SELECT
        r.role_name,
        p.permission_name
    FROM role_permissions rp
    INNER JOIN roles r       ON r.id = rp.role_id
    INNER JOIN permissions p ON p.id = rp.permission_id
    WHERE r.is_active = 1
    """

    with engine.connect() as connection:
        result = connection.execute(text(query))
        rows = result.fetchall()

    mapping: dict[str, set[str]] = {}
    for row in rows:
        role_name = row.role_name
        perm_name = row.permission_name
        if role_name not in mapping:
            mapping[role_name] = set()
        mapping[role_name].add(perm_name)

    return mapping


def get_role_permissions(role_name: str) -> set[str]:
    """
    Get the set of permission names assigned to a role.
    Uses an in-memory cache that is loaded once and can be refreshed.
    """
    global _permission_cache, _cache_loaded

    if not _cache_loaded:
        _permission_cache = _load_permissions()
        _cache_loaded = True

    return _permission_cache.get(role_name, set())


def refresh_permission_cache() -> None:
    """
    Force-reload the permission cache from the database.
    Call this after any role/permission change via the admin API.
    """
    global _permission_cache, _cache_loaded
    _permission_cache = _load_permissions()
    _cache_loaded = True
    logger.info("Permission cache refreshed: %d roles loaded.", len(_permission_cache))


def has_permission(role_name: str, permission_name: str) -> bool:
    """Check if a role has a specific permission."""
    perms = get_role_permissions(role_name)
    return permission_name in perms


# ---------------------------------------------------------------------------
# FastAPI dependency: require_permission(permission_name)
# ---------------------------------------------------------------------------

def require_permission(permission_name: str):

    def permission_checker(user: dict = Depends(get_current_user)) -> dict:

        user_roles = user.get("user_roles", [])

        if not user_roles:
            fallback_role = user.get("role")

            if fallback_role:
                user_roles = [fallback_role]

        authorized = False

        for role_name in user_roles:

            if has_permission(role_name, permission_name):
                authorized = True
                break

        if not authorized:

            logger.warning(
                "Permission denied: user='%s' roles='%s' needs '%s'.",
                user.get("official_email"),
                ",".join(user_roles),
                permission_name,
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: missing permission '{permission_name}'.",
            )

        return user

    return permission_checker


    # ---------------------------------------------------------------------------
    # Lookup helpers for admin APIs
# ---------------------------------------------------------------------------

def get_all_roles() -> list[dict]:
    """Return all roles from the database."""
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id, role_name, description, is_active, created_at
            FROM roles
            ORDER BY id
        """))
        return [dict(row._mapping) for row in result.fetchall()]


def get_all_permissions() -> list[dict]:
    """Return all permissions from the database."""
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id, permission_name, description, category, created_at
            FROM permissions
            ORDER BY category, permission_name
        """))
        return [dict(row._mapping) for row in result.fetchall()]


def get_role_permission_map(role_id: int) -> list[dict]:
    """Return all permissions assigned to a specific role."""
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT p.id, p.permission_name, p.description, p.category
            FROM role_permissions rp
            INNER JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = :role_id
            ORDER BY p.category, p.permission_name
        """), {"role_id": role_id})
        return [dict(row._mapping) for row in result.fetchall()]


def assign_permission_to_role(role_id: int, permission_id: int) -> None:
    """Assign a permission to a role."""
    with engine.begin() as connection:
        connection.execute(text("""
            IF NOT EXISTS (
                SELECT 1 FROM role_permissions
                WHERE role_id = :role_id AND permission_id = :permission_id
            )
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (:role_id, :permission_id)
        """), {"role_id": role_id, "permission_id": permission_id})
    refresh_permission_cache()


def revoke_permission_from_role(role_id: int, permission_id: int) -> None:
    """Remove a permission from a role."""
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM role_permissions
            WHERE role_id = :role_id AND permission_id = :permission_id
        """), {"role_id": role_id, "permission_id": permission_id})
    refresh_permission_cache()
