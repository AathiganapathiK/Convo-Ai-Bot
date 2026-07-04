"""
security/middleware.py

Security middleware for the Enterprise Conversational AI Platform.

Request flow:
    1. JWT Validation      — handled by Auth0 (auth/dependencies.py)
    2. Permission Check    — handled by require_permission() dependency
    3. RLS                 — applied via rls_engine.apply_rls()
    4. SQL Execution       — handled by route handlers
    5. CLS                 — applied via cls_engine.filter_columns()
    6. Audit Logging       — written by audit_service.audit_log()

This module provides:
    - SecurityPipeline: orchestrates the RLS → CLS → Audit chain
    - AuditMiddleware: ASGI middleware for automatic request/response auditing
"""

import time
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from security.rls_engine import apply_rls as rls_apply
from security.cls_engine import validate_cls as cls_validate, filter_columns as cls_filter
from security.audit_service import audit_log, AuditAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SecurityPipeline: one-call chain for the /ask endpoint
# ---------------------------------------------------------------------------

class SecurityPipeline:
    """
    Orchestrates the security pipeline for analytics queries.

    Usage in route handlers:

        pipeline = SecurityPipeline(user)

        # Step 1: Apply RLS to generated SQL
        sql_query, rls_meta = pipeline.apply_rls(sql_query)

        # Step 2: Validate CLS before execution
        is_allowed, cls_message = pipeline.validate_cls(sql_query)

        # Step 3: After execution, filter result columns
        rows = pipeline.filter_columns(rows)

        # Step 4: Log the query
        pipeline.audit_query(question, sql_query, status="SUCCESS")
    """

    def __init__(self, user: dict, ip_address: Optional[str] = None):
        self.user = user
        self.ip_address = ip_address
        self.employee_id = user.get("employee_id", "")
        self.role = user.get("role", "")
        self.rls_metadata: dict = {}

    def apply_rls(self, sql_query: str) -> tuple[str, dict]:
        """Inject RLS filters based on user's data access rules."""
        modified_sql, metadata = rls_apply(sql_query, self.user)
        self.rls_metadata = metadata

        if metadata.get("rls_applied"):
            audit_log(
                user_id=self.employee_id,
                action_type=AuditAction.RLS_APPLIED,
                resource="/ask",
                generated_sql=modified_sql,
                ip_address=self.ip_address,
                metadata=metadata,
            )

        return modified_sql, metadata

    def validate_cls(self, sql_query: str) -> tuple[bool, str]:
        """Validate that the query doesn't reference forbidden columns."""
        is_allowed, message = cls_validate(sql_query, self.role)

        if not is_allowed:
            audit_log(
                user_id=self.employee_id,
                action_type=AuditAction.ACCESS_DENIED,
                resource="/ask",
                generated_sql=sql_query,
                status="DENIED",
                ip_address=self.ip_address,
                metadata={"reason": "CLS_BLOCKED", "message": message},
            )

        return is_allowed, message

    def filter_columns(self, rows: list[dict]) -> list[dict]:
        """Filter result columns based on role CLS rules."""
        filtered = cls_filter(rows, self.role)

        if rows and filtered and len(filtered[0]) < len(rows[0]):
            removed = set(rows[0].keys()) - set(filtered[0].keys())
            audit_log(
                user_id=self.employee_id,
                action_type=AuditAction.CLS_FILTERED,
                resource="/ask",
                ip_address=self.ip_address,
                metadata={"columns_removed": list(removed)},
            )

        return filtered

    def audit_query(
        self,
        question: str,
        sql_query: str,
        status: str = "SUCCESS",
        extra_metadata: Optional[dict] = None,
    ) -> None:
        """Log a CHAT_QUERY audit event."""
        meta = {"rls": self.rls_metadata}
        if extra_metadata:
            meta.update(extra_metadata)

        audit_log(
            user_id=self.employee_id,
            action_type=AuditAction.CHAT_QUERY,
            resource="/ask",
            query_text=question,
            generated_sql=sql_query,
            status=status,
            ip_address=self.ip_address,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# ASGI Middleware: automatic request auditing
# ---------------------------------------------------------------------------

# Paths that should NOT be audit-logged (health checks, static, etc.)
_SKIP_AUDIT_PATHS = {"/", "/health/db", "/docs", "/openapi.json", "/redoc"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that logs every authenticated request to the audit trail.

    This captures high-level request metadata (path, method, status code, timing).
    Detailed audit entries (CHAT_QUERY, EXPORT, etc.) are written by the
    individual route handlers via SecurityPipeline or direct audit_log() calls.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_AUDIT_PATHS:
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration = round(time.time() - start, 3)

        # Extract client IP
        ip = request.client.host if request.client else None

        # Only log non-trivial requests at DEBUG level
        # (detailed audit entries are handled by route handlers)
        logger.debug(
            "Request: %s %s → %d (%.3fs) from %s",
            request.method,
            request.url.path,
            response.status_code,
            duration,
            ip,
        )

        return response
