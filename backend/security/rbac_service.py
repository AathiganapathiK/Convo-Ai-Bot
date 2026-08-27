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

# Explicit Unidirectional Alias Map (Legacy Permission -> Matrix Permission)
# Resolves requested legacy permission from new matrix permission without cross-granting
PERMISSION_ALIAS_MAP = {
    "admin:users:read":    ["page:users:v", "page:roles:v"],
    "admin:users:write":   ["page:users:m", "page:roles:m"],
    "chat:query":          ["chat:ask"],
    "chat:history:read":   ["chat:history"],
    "chat:export":         ["chat:history"],
    "admin:audit:read":    ["page:audit:v"],
    "connections:read":    ["page:connections:v"],
    "connections:write":   ["page:connections:m"],
    "schema:read":         ["page:schema:v"],
    "schema:write":        ["page:schema:m"],
    "semantic:read":       ["page:semantic:v"],
    "semantic:write":      ["page:semantic:m"],
    "providers:read":      ["page:providers:v"],
    "providers:write":     ["page:providers:m"],
    "prompts:read":        ["page:prompts:v"],
    "prompts:write":       ["page:prompts:m"],
    "intents:read":        ["page:intents:v"],
    "intents:write":       ["page:intents:m"],
}

def require_permission(permission_name: str):
    def permission_checker(user: dict = Depends(get_current_user)) -> dict:
        user_roles = user.get("user_roles", [])
        if not user_roles and user.get("role"):
            user_roles = [user["role"]]

        # 1. Check SUPER_ADMIN bypass
        if any(r.upper() == "SUPER_ADMIN" for r in user_roles):
            return user

        employee_id = user.get("employee_id")

        # 2. Check User Overrides from user_data_access (PERM_ALLOW / PERM_DENY)
        allowed_aliases = [permission_name] + PERMISSION_ALIAS_MAP.get(permission_name, [])
        
        with engine.connect() as conn:
            overrides = conn.execute(text("""
                SELECT access_type, access_value
                FROM user_data_access
                WHERE employee_id = :employee_id AND access_type IN ('PERM_ALLOW', 'PERM_DENY')
            """), {"employee_id": employee_id}).fetchall()

            override_denies = {r.access_value for r in overrides if r.access_type == 'PERM_DENY'}
            override_allows = {r.access_value for r in overrides if r.access_type == 'PERM_ALLOW'}

            # Explicit Deny takes highest precedence
            if any(p in override_denies for p in allowed_aliases):
                logger.warning("Permission explicitly denied by user override: user='%s' perm='%s'", employee_id, permission_name)
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied: permission '{permission_name}' revoked by user override.")

            # Explicit Allow grants access
            if any(p in override_allows for p in allowed_aliases):
                return user

        # 3. Inherit from Role permissions
        authorized = False
        for role_name in user_roles:
            role_perms = get_role_permissions(role_name)
            if any(p in role_perms for p in allowed_aliases):
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
