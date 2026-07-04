"""
security/audit_service.py

Centralized audit logging service.

Writes structured audit records to the `audit_logs` table for every
security-relevant action in the platform.

Supported action types:
    LOGIN, LOGOUT, CHAT_QUERY, EXPORT,
    USER_CREATED, USER_UPDATED, ROLE_CHANGED,
    ACCESS_DENIED, RLS_APPLIED, CLS_FILTERED
"""

import json
import logging
from typing import Optional

from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action type constants
# ---------------------------------------------------------------------------

class AuditAction:
    LOGIN           = "LOGIN"
    LOGOUT          = "LOGOUT"
    CHAT_QUERY      = "CHAT_QUERY"
    EXPORT          = "EXPORT"
    USER_CREATED    = "USER_CREATED"
    USER_UPDATED    = "USER_UPDATED"
    ROLE_CHANGED    = "ROLE_CHANGED"
    ACCESS_DENIED   = "ACCESS_DENIED"
    RLS_APPLIED     = "RLS_APPLIED"
    CLS_FILTERED    = "CLS_FILTERED"


# ---------------------------------------------------------------------------
# Core audit function
# ---------------------------------------------------------------------------

def audit_log(
    user_id: Optional[str],
    action_type: str,
    resource: Optional[str] = None,
    query_text: Optional[str] = None,
    generated_sql: Optional[str] = None,
    status: str = "SUCCESS",
    ip_address: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Write an audit log entry to the database.

    Parameters:
        user_id:        Employee ID or email of the acting user.
        action_type:    One of the AuditAction constants.
        resource:       The resource being accessed (e.g. "/ask", "user:1234").
        query_text:     The user's natural-language question (for CHAT_QUERY).
        generated_sql:  The SQL that was generated (for CHAT_QUERY).
        status:         SUCCESS, DENIED, FAILED, etc.
        ip_address:     Client IP address.
        metadata:       Additional structured context (serialized as JSON).
    """
    query = """
    INSERT INTO audit_logs (
        user_id,
        action_type,
        resource,
        query_text,
        generated_sql,
        status,
        ip_address,
        metadata
    )
    VALUES (
        :user_id,
        :action_type,
        :resource,
        :query_text,
        :generated_sql,
        :status,
        :ip_address,
        :metadata
    )
    """

    meta_json = json.dumps(metadata, default=str) if metadata else None

    try:
        with engine.begin() as connection:
            connection.execute(
                text(query),
                {
                    "user_id":       user_id,
                    "action_type":   action_type,
                    "resource":      resource,
                    "query_text":    query_text,
                    "generated_sql": generated_sql,
                    "status":        status,
                    "ip_address":    ip_address,
                    "metadata":      meta_json,
                },
            )
    except Exception as exc:
        # Audit failures must never crash the request pipeline.
        # Log the error and continue.
        logger.error(
            "Failed to write audit log: action=%s user=%s error=%s",
            action_type, user_id, exc,
        )


# ---------------------------------------------------------------------------
# Query helpers (for the admin audit viewer)
# ---------------------------------------------------------------------------

def get_audit_logs(
    company_id: Optional[str] = None,
    limit: int = 100,
    action_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve audit log entries with optional filtering.
    """
    conditions = []
    params: dict = {"limit": limit}

    if company_id:
        conditions.append("u.company_id = :company_id")
        params["company_id"] = company_id

    if action_type:
        conditions.append("al.action_type = :action_type")
        params["action_type"] = action_type

    if user_id:
        conditions.append("al.user_id = :user_id")
        params["user_id"] = user_id

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    query = f"""
    SELECT TOP (:limit)
        al.id,
        al.user_id,
        al.action_type,
        al.resource,
        al.query_text,
        al.generated_sql,
        al.status,
        al.ip_address,
        al.metadata,
        al.created_at
    FROM audit_logs al
    INNER JOIN users u ON u.employee_id = al.user_id
    {where_clause}
    ORDER BY al.created_at DESC
    """

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]
