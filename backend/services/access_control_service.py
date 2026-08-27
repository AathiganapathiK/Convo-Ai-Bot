import logging
from typing import Optional, Dict, List, Set, Any
from sqlalchemy import text, bindparam
from database import engine
from security.rbac_service import refresh_permission_cache

logger = logging.getLogger(__name__)

# List of all managed pages and their permission keys
MANAGED_PAGES = [
    {"key": "overview",         "label": "Overview (Dashboard)",        "path": "/"},
    {"key": "chat",             "label": "Launch Assistant (Chat)",    "path": "/assistant"},
    {"key": "connections",      "label": "Data Sources",               "path": "/connections"},
    {"key": "schema",           "label": "Schema Discovery",           "path": "/schema"},
    {"key": "semantic",         "label": "Semantic Layer",             "path": "/semantic"},
    {"key": "providers",        "label": "AI Providers",               "path": "/providers"},
    {"key": "prompts",          "label": "Prompt Studio",              "path": "/prompts"},
    {"key": "intents",          "label": "Intent Configuration",       "path": "/intents"},
    {"key": "users",            "label": "User Management",            "path": "/users"},
    {"key": "roles",            "label": "Role Management",            "path": "/roles"},
    {"key": "rbac",             "label": "Chat Access Control (RBAC)", "path": "/rbac"},
    {"key": "audit",            "label": "Monitoring & Audit",         "path": "/audit"},
]

# Chat action keys
CHAT_ACTIONS = [
    {"key": "ask",     "code": "A", "label": "Ask Chatbot",          "perm": "chat:ask"},
    {"key": "history", "code": "H", "label": "View Chat History",     "perm": "chat:history"},
    {"key": "delete",  "code": "D", "label": "Delete Chat Sessions",  "perm": "chat:delete"},
]

# Supported Data Scope Dimensions
SCOPE_DIMENSIONS = ["DIVISION", "REGION", "PRODUCT", "CHANNEL"]


class AccessControlService:
    @staticmethod
    def get_master_scopes() -> Dict[str, List[str]]:
        """
        Dynamically fetch available master data scope values for REGION, PRODUCT, CHANNEL, DIVISION
        from user_data_access and system domain definitions.
        """
        base_scopes = {
            "REGION": [
                "Tamil Nadu", "Karnataka", "Kerala", "Andhra Pradesh",
                "Telangana", "North Region", "West Region", "East Region", "Overseas"
            ],
            "PRODUCT": [
                "Sales", "Finance", "HR", "Engineering", "Operations",
                "Marketing", "IT", "Customer Care", "Dispatch", "Retail"
            ],
            "CHANNEL": [
                "Showroom", "Franchise", "Marketing", "Direct", "Online", "Wholesale"
            ],
            "DIVISION": [
                "ACC", "AKG", "ATC", "BandB", "RHL", "RR", "RRF", "TARA", "VGS", "VT",
                "Sales", "Manufacturing", "Finance", "HR", "IT"
            ]
        }
        try:
            with engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT DISTINCT access_type, access_value
                    FROM user_data_access
                    WHERE access_type IN ('REGION', 'PRODUCT', 'CHANNEL', 'DIVISION')
                """)).fetchall()

                for row in res:
                    at = row.access_type.upper()
                    val = row.access_value
                    if at in base_scopes and val and val not in base_scopes[at]:
                        base_scopes[at].append(val)
        except Exception as e:
            logger.error(f"Error loading dynamic master scopes: {e}")

        return base_scopes

    @staticmethod
    def get_role_matrix(role_id: int) -> Dict[str, Any]:
        """
        Get Page Access (V/M), Chat Access (A/H/D), and Data Scope for a role.
        """
        with engine.connect() as conn:
            # 1. Fetch assigned permissions for this role
            res = conn.execute(text("""
                SELECT p.permission_name
                FROM role_permissions rp
                INNER JOIN permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = :role_id
            """), {"role_id": role_id}).fetchall()
            
            assigned_perms = {r.permission_name for r in res}

            # 2. Build Page Access V/M
            page_access = {}
            for page in MANAGED_PAGES:
                k = page["key"]
                page_access[k] = {
                    "v": f"page:{k}:v" in assigned_perms,
                    "m": f"page:{k}:m" in assigned_perms
                }

            # 3. Build Chat Access A/H/D
            chat_access = {
                "a": "chat:ask" in assigned_perms,
                "h": "chat:history" in assigned_perms,
                "d": "chat:delete" in assigned_perms
            }

            # 4. Fetch Role Data Scope from user_data_access / role_data_access (using ROLE_ prefix or user_data_access fallback)
            scope_res = conn.execute(text("""
                SELECT access_type, access_value
                FROM user_data_access
                WHERE employee_id = :role_key
            """), {"role_key": f"ROLE_{role_id}"}).fetchall()

            data_scope = {dim: [] for dim in SCOPE_DIMENSIONS}
            for row in scope_res:
                access_type = row.access_type.upper()
                if access_type in data_scope:
                    data_scope[access_type].append(row.access_value)

            return {
                "role_id": role_id,
                "page_access": page_access,
                "chat_access": chat_access,
                "data_scope": data_scope
            }

    @staticmethod
    def save_role_matrix(
        role_id: int,
        page_access: Dict[str, Dict[str, bool]],
        chat_access: Dict[str, bool],
        data_scope: Dict[str, List[str]],
        updated_by: Optional[str] = None
    ) -> None:
        """
        Update Page Access V/M, Chat Access A/H/D, and Data Scope for a role.
        """
        with engine.begin() as conn:
            # Resolve permission IDs to set
            target_perm_names = set()
            for page_key, vm in page_access.items():
                if vm.get("v"):
                    target_perm_names.add(f"page:{page_key}:v")
                if vm.get("m"):
                    target_perm_names.add(f"page:{page_key}:m")

            if chat_access.get("a"):
                target_perm_names.add("chat:ask")
            if chat_access.get("h"):
                target_perm_names.add("chat:history")
            if chat_access.get("d"):
                target_perm_names.add("chat:delete")

            # Remove existing page/chat permissions for role
            conn.execute(text("""
                DELETE FROM role_permissions
                WHERE role_id = :role_id
                  AND permission_id IN (
                      SELECT id FROM permissions
                      WHERE category IN ('page_view', 'page_modify', 'chat_action') 
                         OR permission_name LIKE 'page:%' OR permission_name LIKE 'chat:%'
                  )
            """), {"role_id": role_id})

            # Insert new permissions
            if target_perm_names:
                stmt = text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role_id, id
                    FROM permissions
                    WHERE permission_name IN :perm_names
                """).bindparams(bindparam("perm_names", expanding=True))
                conn.execute(stmt, {"role_id": role_id, "perm_names": list(target_perm_names)})

            # Update Role Data Scopes
            role_key = f"ROLE_{role_id}"
            conn.execute(text("DELETE FROM user_data_access WHERE employee_id = :role_key"), {"role_key": role_key})

            for dim, values in data_scope.items():
                dim_upper = dim.upper()
                if dim_upper in SCOPE_DIMENSIONS and values:
                    for val in values:
                        if val:
                            conn.execute(text("""
                                INSERT INTO user_data_access (employee_id, access_type, access_value, created_by)
                                VALUES (:role_key, :access_type, :access_value, :created_by)
                            """), {
                                "role_key": role_key,
                                "access_type": dim_upper,
                                "access_value": str(val),
                                "created_by": updated_by or "SYSTEM"
                            })

        refresh_permission_cache()

    @staticmethod
    def get_effective_user_matrix(user: dict) -> Dict[str, Any]:
        """
        Get Effective Page V/M, Chat A/H/D, and Scopes for a specific authenticated user.
        Precedence: Explicit User Scopes / Overrides → Role Permissions & Scopes.
        """
        employee_id = user.get("employee_id")
        user_roles = user.get("user_roles", [])
        if not user_roles and user.get("role"):
            user_roles = [user["role"]]

        role_names = user_roles if user_roles else ["__NONE__"]

        with engine.connect() as conn:
            # Build safe parameter placeholders for PyODBC SQL Server compatibility
            role_params = {f"role_{i}": r for i, r in enumerate(role_names)}
            role_placeholders = ", ".join([f":role_{i}" for i in range(len(role_names))])

            # Fetch all permissions granted to user's active roles
            res = conn.execute(text(f"""
                SELECT p.permission_name
                FROM role_permissions rp
                INNER JOIN roles r ON r.id = rp.role_id
                INNER JOIN permissions p ON p.id = rp.permission_id
                WHERE r.role_name IN ({role_placeholders}) AND r.is_active = 1
            """), role_params).fetchall()

            role_perms = {r.permission_name for r in res}

            # Check SUPER_ADMIN bypass
            is_super_admin = any(r.upper() == "SUPER_ADMIN" for r in role_names)

            # Build Page V/M
            page_access = {}
            for page in MANAGED_PAGES:
                k = page["key"]
                page_access[k] = {
                    "v": is_super_admin or (f"page:{k}:v" in role_perms),
                    "m": is_super_admin or (f"page:{k}:m" in role_perms)
                }

            # Build Chat A/H/D
            chat_access = {
                "a": is_super_admin or ("chat:ask" in role_perms or "chat:query" in role_perms),
                "h": is_super_admin or ("chat:history" in role_perms or "chat:history:read" in role_perms),
                "d": is_super_admin or ("chat:delete" in role_perms)
            }

            # Resolve Scopes for user (from user_data_access for employee_id and user's role keys)
            data_scope = {dim: [] for dim in SCOPE_DIMENSIONS}

            # 1. Fetch user-specific data access
            user_scopes = conn.execute(text("""
                SELECT access_type, access_value
                FROM user_data_access
                WHERE employee_id = :employee_id
            """), {"employee_id": employee_id}).fetchall()

            for row in user_scopes:
                access_type = row.access_type.upper()
                if access_type in data_scope:
                    data_scope[access_type].append(row.access_value)

            # 2. Intersect or fallback with role scopes to prevent unauthorized user scope expansion
            role_rows = conn.execute(text(f"""
                SELECT id FROM roles WHERE role_name IN ({role_placeholders})
            """), role_params).fetchall()

            role_keys = [f"ROLE_{r.id}" for r in role_rows]
            role_data_scope = {dim: [] for dim in SCOPE_DIMENSIONS}
            if role_keys:
                rk_params = {f"rk_{i}": k for i, k in enumerate(role_keys)}
                rk_placeholders = ", ".join([f":rk_{i}" for i in range(len(role_keys))])
                role_scopes = conn.execute(text(f"""
                    SELECT access_type, access_value
                    FROM user_data_access
                    WHERE employee_id IN ({rk_placeholders})
                """), rk_params).fetchall()

                for row in role_scopes:
                    access_type = row.access_type.upper()
                    if access_type in role_data_scope:
                        role_data_scope[access_type].append(row.access_value)


            for dim in SCOPE_DIMENSIONS:
                if not data_scope[dim]:
                    data_scope[dim] = role_data_scope[dim]
                elif role_data_scope[dim] and not is_super_admin:
                    # Enforce security boundary: user scope must be within allowed role boundary
                    allowed_set = set(role_data_scope[dim])
                    data_scope[dim] = [v for v in data_scope[dim] if v in allowed_set]


            return {
                "employee_id": employee_id,
                "roles": role_names,
                "is_super_admin": is_super_admin,
                "page_access": page_access,
                "chat_access": chat_access,
                "data_scope": data_scope
            }

    @staticmethod
    def get_user_matrix(employee_id: str) -> Dict[str, Any]:
        """
        Fetch matrix settings for a specific user, including explicit overrides (ALLOW / DENY / INHERIT).
        """
        with engine.connect() as conn:
            overrides = conn.execute(text("""
                SELECT access_type, access_value
                FROM user_data_access
                WHERE employee_id = :employee_id
            """), {"employee_id": employee_id}).fetchall()

            page_overrides = {}
            chat_overrides = {}
            data_scope = {dim: [] for dim in SCOPE_DIMENSIONS}

            for row in overrides:
                at = row.access_type.upper()
                val = row.access_value
                if at in ('PERM_ALLOW', 'PERM_DENY'):
                    is_allow = (at == 'PERM_ALLOW')
                    if val.startswith("page:"):
                        parts = val.split(":")
                        if len(parts) == 3:
                            pk, mode = parts[1], parts[2]
                            if pk not in page_overrides:
                                page_overrides[pk] = {}
                            page_overrides[pk][mode] = "allowed" if is_allow else "denied"
                    elif val.startswith("chat:"):
                        parts = val.split(":")
                        if len(parts) == 2:
                            ck = parts[1]
                            code_map = {"ask": "a", "history": "h", "delete": "d", "query": "a"}
                            if ck in code_map:
                                chat_overrides[code_map[ck]] = "allowed" if is_allow else "denied"
                elif at in data_scope:
                    data_scope[at].append(val)

            return {
                "employee_id": employee_id,
                "page_overrides": page_overrides,
                "chat_overrides": chat_overrides,
                "data_scope": data_scope
            }

    @staticmethod
    def save_user_matrix(
        employee_id: str,
        page_overrides: Dict[str, Dict[str, str]],
        chat_overrides: Dict[str, str],
        data_scope: Dict[str, List[str]],
        updated_by: Optional[str] = None
    ) -> None:
        """
        Save explicit user-level permission overrides (PERM_ALLOW, PERM_DENY) and user data scopes.
        """
        with engine.begin() as conn:
            # Clear existing user permission overrides and data scopes
            conn.execute(text("DELETE FROM user_data_access WHERE employee_id = :employee_id"), {"employee_id": employee_id})

            # Save Page permission overrides
            for pk, vm in page_overrides.items():
                for mode in ('v', 'm'):
                    st = vm.get(mode)
                    if st in ('allowed', 'denied'):
                        conn.execute(text("""
                            INSERT INTO user_data_access (employee_id, access_type, access_value, created_by)
                            VALUES (:employee_id, :access_type, :access_value, :created_by)
                        """), {
                            "employee_id": employee_id,
                            "access_type": "PERM_ALLOW" if st == "allowed" else "PERM_DENY",
                            "access_value": f"page:{pk}:{mode}",
                            "created_by": updated_by or "SYSTEM"
                        })

            # Save Chat permission overrides
            chat_map = {"a": "chat:ask", "h": "chat:history", "d": "chat:delete"}
            for ck, st in chat_overrides.items():
                if ck in chat_map and st in ('allowed', 'denied'):
                    conn.execute(text("""
                        INSERT INTO user_data_access (employee_id, access_type, access_value, created_by)
                        VALUES (:employee_id, :access_type, :access_value, :created_by)
                    """), {
                        "employee_id": employee_id,
                        "access_type": "PERM_ALLOW" if st == "allowed" else "PERM_DENY",
                        "access_value": chat_map[ck],
                        "created_by": updated_by or "SYSTEM"
                    })

            # Save User Data Scopes
            for dim, values in data_scope.items():
                dim_upper = dim.upper()
                if dim_upper in SCOPE_DIMENSIONS and values:
                    for val in values:
                        if val:
                            conn.execute(text("""
                                INSERT INTO user_data_access (employee_id, access_type, access_value, created_by)
                                VALUES (:employee_id, :access_type, :access_value, :created_by)
                            """), {
                                "employee_id": employee_id,
                                "access_type": dim_upper,
                                "access_value": str(val),
                                "created_by": updated_by or "SYSTEM"
                            })

        refresh_permission_cache()

