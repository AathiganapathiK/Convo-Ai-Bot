import sys
if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr is not None and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from ai.chart_generator import generate_kpis
from ai import chart_generator
import os
import json
import time
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from auth.auth_router import router as auth_router
from auth.dependencies import get_current_user
from database import engine

from ai.sql_validator import validate_sql_query, enforce_row_limit
from ai.prompt_builder import build_summary_prompt
from ai.intent_classifier import classify_intent
from ai.ai_service import generate_sql_query, generate_business_summary
from ai.general_chat import generate_general_response
from ai.chart_generator import generate_chart_metadata

from services.conversation_memory import get_history, add_exchange
from services.query_history_service import save_query_history
from services.usage_tracking_service import save_usage
from services.export_service import create_excel_report
from services.db_service import DBService
from services.config_service import ConfigService
from services.auth_service import AuthService
from services.schema_monitor_service import SchemaMonitorService
from services.connection_manager import (ConnectionManager)
from services.connection_service import ConnectionService
from services.qdrant_service import QdrantService
from services.column_display_service import ColumnDisplayService


from semantic.discovery_service import SemanticDiscoveryService
from semantic.semantic_context_service import SemanticContextService
from semantic.semantic_resolver import SemanticResolver
from semantic.relationship_service import SemanticRelationshipService
from semantic.query_examples_service import QueryExamplesService
from services.connection_service import ConnectionService
from semantic.relevant_table_resolver import RelevantTableResolver
from semantic.relevant_schema_service import RelevantSchemaService
from semantic.relationship_expander import RelationshipExpander
from semantic.semantic_service import SemanticService
from semantic.semantic_schema import MetricRequest,DimensionRequest

# --- New Security Framework ---
from security.rbac_service import require_permission
from security.middleware import SecurityPipeline, AuditMiddleware
from security.audit_service import audit_log, AuditAction

from admin.user_management import router as admin_router
from admin.role_management import router as role_router
from admin.user_role_management import router as user_role_router
from admin.provider_management import router as provider_router
from admin.provider_credentials import router as provider_credentials_router
from admin.connection_management import router as connection_router

from core.exceptions import DatasourceLifecycleException

from core.exception_handlers import (
    datasource_exception_handler,
    generic_exception_handler
)

from chat.chat_sessions import router as chat_router

from configuration.config_routes import (router as config_router)


BASE_DIR = Path(__file__).resolve().parent

if not os.getenv("APP_ENV"):
    load_dotenv(BASE_DIR / ".env")
QdrantService.initialize()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database Schema and Isolation Initialization
# ---------------------------------------------------------------------------

def initialize_company_isolation():
    try:
        with engine.begin() as connection:
            # Add company_id to user_queries
            connection.execute(text("""
                IF NOT EXISTS (
                    SELECT * FROM sys.columns 
                    WHERE object_id = OBJECT_ID('user_queries') AND name = 'company_id'
                )
                BEGIN
                    ALTER TABLE user_queries ADD company_id UNIQUEIDENTIFIER NULL;
                END
            """))
            # Add company_id to user_usage
            connection.execute(text("""
                IF NOT EXISTS (
                    SELECT * FROM sys.columns 
                    WHERE object_id = OBJECT_ID('user_usage') AND name = 'company_id'
                )
                BEGIN
                    ALTER TABLE user_usage ADD company_id UNIQUEIDENTIFIER NULL;
                END
            """))
            # Backfill legacy queries
            connection.execute(text("""
                UPDATE uq
                SET uq.company_id = u.company_id
                FROM user_queries uq
                INNER JOIN users u ON u.employee_id = uq.employee_id
                WHERE uq.company_id IS NULL;
            """))
            # Backfill legacy usage logs
            connection.execute(text("""
                UPDATE uu
                SET uu.company_id = u.company_id
                FROM user_usage uu
                INNER JOIN users u ON u.employee_id = uu.employee_id
                WHERE uu.company_id IS NULL;
            """))
    except Exception as e:
        logger.error(f"Error initializing company isolation schemas: {e}")

initialize_company_isolation()

def validate_prompt_tables_in_metadata():
    try:
        from ai.schema_loader import ALLOWED_TABLES
        with engine.connect() as conn:
            result = conn.execute(text("SELECT schema_name, table_name FROM schema_tables")).fetchall()
            metadata_tables = {f"{row._mapping['schema_name']}.{row._mapping['table_name']}" for row in result}
            
        missing_tables = ALLOWED_TABLES - metadata_tables
        if missing_tables:
            msg = f"[STARTUP VALIDATION ERROR] The following required prompt tables are missing from database schema_tables metadata: {', '.join(missing_tables)}. Please run schema sync."
            logger.error(msg)
            print(msg)
        else:
            msg = "Startup validation passed: all required prompt tables exist in database metadata."
            logger.info(msg)
            print(msg)
    except Exception as e:
        msg = f"Error during startup prompt tables validation: {e}"
        logger.error(msg)
        print(msg)

validate_prompt_tables_in_metadata()


SchemaMonitorService.start()


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Enterprise Conversational AI API",
    description="Auth0-authenticated, RBAC/CLS/RLS-enforced analytics backend.",
    version="2.0.0",
)

app.add_exception_handler(
    DatasourceLifecycleException,
    datasource_exception_handler
)

app.add_exception_handler(
    Exception,
    generic_exception_handler
)

_frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Company-ID"],
)

# Audit middleware — logs all requests
app.add_middleware(AuditMiddleware)

security = HTTPBearer()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _save_chat_message(
session_id: int,
role: str,
message_text: str,
sql_query: str | None = None,
business_summary: str | None = None,
result_data: str | None = None,
chart_metadata: str | None = None,
followup_questions: str | None = None,
) -> None:

    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO chat_messages
                (
                    session_id,
                    role,
                    message_text,
                    sql_query,
                    business_summary,
                    result_data,
                    chart_metadata,
                    followup_questions
                )
                VALUES
                (
                    :session_id,
                    :role,
                    :message_text,
                    :sql_query,
                    :business_summary,
                    :result_data,
                    :chart_metadata,
                    :followup_questions
                )
            """),
            {
                "session_id":       session_id,
                "role":             role,
                "message_text":     message_text,
                "sql_query":        sql_query,
                "business_summary": business_summary,
                "result_data":      result_data,
                "chart_metadata":   chart_metadata,
                "followup_questions": followup_questions,
            },
        )

# ---------------------------------------------------------------------------
# Health / auth test
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {"message": "Retail AI Backend Running"}


@app.get("/auth-test")
def auth_test(user: dict = Depends(get_current_user)):
    """Returns the authenticated user's DB-loaded profile. Use for smoke-testing."""
    return user



@app.get("/health/db")
def health_db():
    """Test database connection. No authentication required."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "✓ Database connection successful",
            "database": "healthy"
        }
    except Exception as e:
        return {
            "status": "✗ Database connection failed",
            "error": str(e),
            "database": "unhealthy"
        }
    
@app.get("/test/query")
def test_query(
    question: str,
    user: dict = Depends(require_permission("system:debug"))
):
    """Test endpoint for queries. Requires system:debug permission."""
    try:
        intent = classify_intent(question)

        if intent == "GENERAL":
            response = generate_general_response(question)
        else:
            response = generate_sql_query(question)

        return {
            "question": question,
            "intent": intent,
            "response": response,
        }
    
    except Exception as e:
        return {"error": str(e), "question": question}


@app.post("/test/sql")
def test_sql(
    sql_query: str,
    user: dict = Depends(require_permission("system:debug")),
):
    """Execute raw SQL query directly. Requires system:debug permission."""
    try:

        source_engine = (
                ConnectionManager.source(
                    user["company_id"]
                )
            )

        with source_engine.connect() as connection:
            result = connection.execute(
                text(sql_query)
            )
            rows = result.fetchall()
            columns = result.keys()
            data = [dict(row._mapping) for row in rows]

            return {
                "success": True,
                "query": sql_query,
                "row_count": len(data),
                "columns": list(columns),
                "data": data,
            }
    except Exception as e:
        return {"success": False, "query": sql_query, "error": str(e)}


# ---------------------------------------------------------------------------
# Analytics — /ask
# ---------------------------------------------------------------------------

@app.get("/ask")
def ask_question(
    question: str,
    session_id: int,
    request: Request,
    user: dict = Depends(require_permission("chat:query")),
):
    client_ip = request.client.host if request.client else None

    # Validate session access
    with engine.connect() as connection:
        session_row = connection.execute(
            text("SELECT employee_id, company_id FROM chat_sessions WHERE id = :session_id"),
            {"session_id": session_id}
        ).fetchone()

    if not session_row:
        raise HTTPException(status_code=404, detail="Chat session not found")

    session_row = dict(session_row._mapping)
    caller_role = user.get("role", "").upper()

    if str(session_row["company_id"]) != str(user["company_id"]):
        raise HTTPException(status_code=403, detail="Access denied: chat session belongs to another company.")

    if caller_role != "SUPER_ADMIN" and session_row["employee_id"] != user["employee_id"]:
        raise HTTPException(status_code=403, detail="Access denied: chat session belongs to another user.")

    # Persist user message
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO chat_messages (session_id, role, message_text)
                VALUES (:session_id, 'USER', :message_text)
            """),
            {"session_id": session_id, "message_text": question},
        )

    # Classify intent
    intent = classify_intent(question, company_id=user["company_id"])

    if intent == "GENERAL":
        response_text: str = generate_general_response(question)
        _save_chat_message(
            session_id=session_id,
            role="ASSISTANT",
            message_text=response_text,
        )
        audit_log(
            user_id=user["employee_id"],
            action_type=AuditAction.CHAT_QUERY,
            resource="/ask",
            query_text=question,
            status="SUCCESS",
            ip_address=client_ip,
            metadata={"intent": "GENERAL"},
        )
        return {"type": "GENERAL", "message": response_text}

    # --- Security Pipeline: RLS → CLS → Audit ---
    print("\n========== REQUEST ==========")
    print(f"Question: {question}")

    pipeline = SecurityPipeline(user, ip_address=client_ip)

    # Analytics path
    history = get_history(user["employee_id"], str(session_id))

    sql_response = generate_sql_query(question, history, company_id=user["company_id"])
    sql_query: str = sql_response.get("sql_query") or ""
    sql_usage    = sql_response["usage"]

    sql_prompt_tokens = sql_usage.prompt_tokens if sql_usage is not None else 0
    sql_completion_tokens = sql_usage.completion_tokens if sql_usage is not None else 0
    sql_total_tokens = sql_usage.total_tokens if sql_usage is not None else 0
    save_usage(
        user["employee_id"], session_id, "SQL_GENERATION",
        sql_prompt_tokens, sql_completion_tokens,
        sql_total_tokens, 0, user["company_id"]
    )

    # CLS validation (pre-execution)
    is_allowed, cls_message = pipeline.validate_cls(sql_query)

    if not is_allowed:
        save_query_history(
            user["employee_id"], session_id, question,
            sql_query, "CLS_BLOCKED", 0, user["company_id"]
        )
        return {"error": cls_message}

    # SQL safety validation
    is_valid, validation_message = validate_sql_query(sql_query)

    if not is_valid:
        save_query_history(
            user["employee_id"], session_id, question,
            sql_query, "SQL_VALIDATION_FAILED", 0, user["company_id"]
        )
        return {"error": validation_message}

    # Enforce row limit
    sql_query = enforce_row_limit(sql_query)

    # RLS injection (database-driven)
    sql_query, rls_meta = pipeline.apply_rls(sql_query)

    start_time = time.time()
    try:
        active_connection = ConnectionService.get_active_connection(user["company_id"])
        if not active_connection:
            raise Exception("No active database connection configured")

        source_engine = (
                ConnectionManager.source(
                    user["company_id"],
                    connection=active_connection
                )
            )

        with source_engine.connect() as connection:
            result = connection.execute(
                text(sql_query)
            )

            keys = list(result.keys())
            rows = []
            for r in result.fetchall():
                row_dict = {}
                empty_col_idx = 1
                for idx, col_name in enumerate(keys):
                    if col_name == "":
                        new_key = "Value" if empty_col_idx == 1 else f"Value_{empty_col_idx}"
                        row_dict[new_key] = r[idx]
                        empty_col_idx += 1
                    else:
                        row_dict[col_name] = r[idx]
                rows.append(row_dict)

        # Column Display Configuration (Metadata Layer)
        rows = ColumnDisplayService.apply_display_config(
            rows=rows,
            connection_id=active_connection["connection_id"]
        )

        # CLS column filtering (Security Layer)
        rows = pipeline.filter_columns(rows)

        execution_time = round(time.time() - start_time, 2)

        print("\n========== EXECUTION ==========")
        print(f"Rows Returned: {len(rows)}")
        print(f"Execution Time: {execution_time}s")

        summary_response = generate_business_summary(
            question,
            sql_query,
            rows,
            company_id=user["company_id"]
        )

        business_summary = (
            summary_response["summary"]
        )

        followup_questions = (
            summary_response["followups"]
        )

        chart_result = generate_chart_metadata(
            question=question,
            rows=rows
        )
        kpis = generate_kpis(rows)

        if isinstance(
            chart_result,
            tuple
        ):
            chart_metadata, chart_rows = (
                chart_result
            )
        else:
            chart_metadata = chart_result
            chart_rows = rows

        print("\n========== CHART ==========")
        print(f"Recommended View: {chart_metadata.get('recommended_view', 'table') if chart_metadata else 'table'}")
        print("Chart Generated ✓")

        summary_usage      = summary_response["usage"]

        sum_prompt_tokens = summary_usage.prompt_tokens if summary_usage is not None else 0
        sum_completion_tokens = summary_usage.completion_tokens if summary_usage is not None else 0
        sum_total_tokens = summary_usage.total_tokens if summary_usage is not None else 0
        save_usage(
            user["employee_id"], session_id, "SUMMARY_GENERATION",
            sum_prompt_tokens, sum_completion_tokens,
            sum_total_tokens, 0, user["company_id"]
        )

        result_data    = json.dumps(rows, default=str)

        chart_data = json.dumps(chart_metadata, default=str)

        _save_chat_message(
            session_id=session_id,
            role="ASSISTANT",
            message_text=business_summary or "",
            sql_query=sql_query,
            business_summary=business_summary,
            result_data=result_data,
            chart_metadata=chart_data,
            followup_questions=json.dumps(followup_questions)
        )

        add_exchange(user["employee_id"], question, sql_query, str(session_id))

        save_query_history(
            user["employee_id"], session_id, question,
            sql_query, "SUCCESS", execution_time, user["company_id"]
        )

        # Audit: successful query
        pipeline.audit_query(question, sql_query, status="SUCCESS",
                             extra_metadata={"execution_time": execution_time, "rows": len(rows)})

        print("\n========== COMPLETE ==========")
        print("Request completed successfully.")
                             
        if rows:
            QueryExamplesService.store(
                question=question,
                sql_query=sql_query,
                connection_id=active_connection["connection_id"]
            )

        return {
            "sql_query":        sql_query,
            "data":             rows,
            "chart_data":       chart_rows,
            "business_summary": business_summary,
            "followup_questions":followup_questions,
            "chart":            chart_metadata,
            "kpis":             kpis
        }

    except Exception as exc:
        logger.error(
            "SQL execution failed for user='%s', session=%d: %s",
            user["official_email"], session_id, exc,
        )
        save_query_history(
            user["employee_id"], session_id, question,
            sql_query, "FAILED", 0, user["company_id"]
        )
        pipeline.audit_query(question, sql_query, status="FAILED",
                             extra_metadata={"error": str(exc)})
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.post("/export-excel")
def export_excel(
    payload: dict,
    request: Request,
    user: dict = Depends(require_permission("chat:export")),
):
    excel_file = create_excel_report(
        payload["question"],
        payload["summary"],
        payload["data"],
    )
    audit_log(
        user_id=user["employee_id"],
        action_type=AuditAction.EXPORT,
        resource="/export-excel",
        query_text=payload.get("question"),
        ip_address=request.client.host if request.client else None,
        metadata={"rows_exported": len(payload.get("data", []))},
    )
    return StreamingResponse(
        excel_file,
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": "attachment; filename=analytics_report.xlsx"
        },
    )


# ---------------------------------------------------------------------------
# Companies (SUPER_ADMIN Switched Contexts)
# ---------------------------------------------------------------------------

@app.get("/companies")
def get_companies(user: dict = Depends(get_current_user)):
    return [
        {
            "company_id": user["company_id"],
            "company_name": user["company_name"],
            "company_code": user["company_code"]
        }
    ]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.get("/profile")
def get_profile(user: dict = Depends(get_current_user)):
    """
    Returns the authenticated user's full profile from the DB.
    Since get_current_user() already fetches from DB, we do a targeted
    profile query for the extra optional fields.
    """
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    employee_id,
                    full_name,
                    official_email,
                    company,
                    department,
                    role,
                    location,
                    mobile_number,
                    address
                FROM users
                WHERE official_email = :email
            """),
            {"email": user["official_email"]},
        )
        profile = result.fetchone()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found.",
        )

    return dict(profile._mapping)


@app.put("/profile")
def update_profile(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE users
                SET
                    mobile_number = :mobile_number,
                    address       = :address
                WHERE official_email = :email
            """),
            {
                "mobile_number": payload.get("mobile_number"),
                "address":       payload.get("address"),
                "email":         user["official_email"],
            },
        )
    return {"message": "Profile updated successfully"}


# ---------------------------------------------------------------------------
# Query history
# ---------------------------------------------------------------------------

@app.get("/query-history")
def get_query_history(user: dict = Depends(require_permission("chat:history:read"))):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        query = """
            SELECT id, session_id, question, sql_query, execution_status, execution_time, created_at
            FROM user_queries
            WHERE company_id = :company_id
            ORDER BY created_at DESC
        """
        params = {"company_id": user["company_id"]}
    else:
        query = """
            SELECT id, session_id, question, sql_query, execution_status, execution_time, created_at
            FROM user_queries
            WHERE employee_id = :employee_id AND company_id = :company_id
            ORDER BY created_at DESC
        """
        params = {"employee_id": user["employee_id"], "company_id": user["company_id"]}

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]


@app.get("/query-history/{session_id}")
def get_session_query_history(
    session_id: int,
    user: dict = Depends(require_permission("chat:history:read")),
):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        query = """
            SELECT id, question, sql_query, execution_status, execution_time, created_at
            FROM user_queries
            WHERE session_id = :session_id AND company_id = :company_id
            ORDER BY created_at DESC
        """
        params = {"session_id": session_id, "company_id": user["company_id"]}
    else:
        query = """
            SELECT id, question, sql_query, execution_status, execution_time, created_at
            FROM user_queries
            WHERE employee_id = :employee_id AND session_id = :session_id AND company_id = :company_id
            ORDER BY created_at DESC
        """
        params = {"employee_id": user["employee_id"], "session_id": session_id, "company_id": user["company_id"]}

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]


@app.get("/dashboard/query-trends")
def get_query_trends(
    group_by: str = "hour",
    user: dict = Depends(require_permission("chat:history:read")),
):
    group_by = group_by.lower()
    if group_by not in ("hour", "day", "week"):
        raise HTTPException(status_code=400, detail="Invalid group_by parameter. Choose 'hour', 'day', or 'week'.")

    company_id = user["company_id"]

    if group_by == "hour":
        query = """
            SELECT 
                FORMAT(created_at, 'HH:00') AS label,
                COUNT(id) AS query_count,
                ROUND(COALESCE(AVG(CAST(execution_time AS FLOAT)), 0), 2) AS latency
            FROM user_queries
            WHERE company_id = :company_id
              AND created_at >= DATEADD(day, -1, GETDATE())
            GROUP BY FORMAT(created_at, 'HH:00'), DATEPART(hour, created_at)
            ORDER BY DATEPART(hour, created_at)
        """
    elif group_by == "day":
        query = """
            SELECT 
                FORMAT(created_at, 'yyyy-MM-dd') AS label,
                COUNT(id) AS query_count,
                ROUND(COALESCE(AVG(CAST(execution_time AS FLOAT)), 0), 2) AS latency
            FROM user_queries
            WHERE company_id = :company_id
              AND created_at >= DATEADD(day, -7, GETDATE())
            GROUP BY FORMAT(created_at, 'yyyy-MM-dd'), CAST(created_at AS DATE)
            ORDER BY CAST(created_at AS DATE)
        """
    else: # week
        query = """
            SELECT 
                CONCAT('Week ', DATEPART(week, created_at)) AS label,
                COUNT(id) AS query_count,
                ROUND(COALESCE(AVG(CAST(execution_time AS FLOAT)), 0), 2) AS latency
            FROM user_queries
            WHERE company_id = :company_id
              AND created_at >= DATEADD(week, -4, GETDATE())
            GROUP BY DATEPART(week, created_at)
            ORDER BY DATEPART(week, created_at)
        """

    with engine.connect() as connection:
        res = connection.execute(text(query), {"company_id": company_id}).fetchall()
        rows = [dict(row._mapping) for row in res]

    return {
        "labels": [r["label"] for r in rows],
        "query_count": [r["query_count"] for r in rows],
        "latency": [r["latency"] for r in rows]
    }

# ---------------------------------------------------------------------------
# Dashboard KPI endpoint
# ---------------------------------------------------------------------------
@app.get("/dashboard/kpis")
def get_dashboard_kpis(user: dict = Depends(require_permission("chat:history:read"))):
    """Return KPI metrics scoped to the user's company."""
    company_id = user["company_id"]
    # Total executed queries
    total_res = engine.connect().execute(text(
        "SELECT COUNT(*) AS total FROM user_queries WHERE company_id = :cid"
    ), {"cid": company_id}).fetchone()
    total_queries = total_res._mapping["total"] if total_res else 0

    # Average pipeline latency for successful queries
    avg_res = engine.connect().execute(text(
        "SELECT AVG(CAST(execution_time AS FLOAT)) AS avg_latency FROM user_queries WHERE execution_status = 'SUCCESS' AND company_id = :cid"
    ), {"cid": company_id}).fetchone()
    avg_latency = 0.0
    if avg_res:
        val = avg_res._mapping["avg_latency"]
        if val is not None:
            avg_latency = round(float(val), 2)

    # Success percentage
    success_res = engine.connect().execute(text(
        "SELECT COUNT(*) AS success_count FROM user_queries WHERE execution_status = 'SUCCESS' AND company_id = :cid"
    ), {"cid": company_id}).fetchone()
    success_count = success_res._mapping["success_count"] if success_res else 0
    success_pct = (success_count / total_queries * 100) if total_queries else 0
    success_pct = round(success_pct, 2)

    # Security policy blocks (audit logs with denied actions)
    blocks_res = engine.connect().execute(text(
        "SELECT COUNT(*) AS blocks FROM audit_logs WHERE action_type = 'ACCESS_DENIED'"
    )).fetchone()
    security_blocks = blocks_res._mapping["blocks"] if blocks_res else 0

    return {
        "total_queries": total_queries,
        "avg_latency": avg_latency,
        "success_pct": success_pct,
        "security_blocks": security_blocks,
    }
# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------

@app.get("/memory")
def view_memory(user: dict = Depends(require_permission("chat:query"))):
    return get_history(user["employee_id"], "default")


# ---------------------------------------------------------------------------
# Debug / test endpoints (RLS + CLS) — requires system:debug permission
# ---------------------------------------------------------------------------

@app.get("/test-rls")
def test_rls(user: dict = Depends(require_permission("system:debug"))):
    from security.rls_engine import apply_rls
    base_sql = "SELECT TOP 100 * FROM Sales"
    sql_query, rls_meta = apply_rls(base_sql, user)


    source_engine = (
                ConnectionManager.source(
                    user["company_id"]
                )
            )

    with source_engine.connect() as connection:
        result = connection.execute(
            text(sql_query)
        )

        rows   = [dict(row._mapping) for row in result.fetchall()]
    
    return {
        "role":       user["role"],
        "final_sql":  sql_query,
        "rls_meta":   rls_meta,
        "row_count":  len(rows),
        "sample_rows": rows[:5],
    }


@app.get("/test-cls")
def test_cls(user: dict = Depends(require_permission("system:debug"))):
    from security.cls_engine import validate_cls, filter_columns
    sql_query = "SELECT TOP 100 Sales, Cost, Quantity FROM Sales"
    is_allowed, message = validate_cls(sql_query, user["role"])
    if not is_allowed:
        return {"error": message}

    source_engine = (
        ConnectionManager.source(
            user["company_id"]
        )
    )

    with source_engine.connect() as connection:
        result = connection.execute(
            text(sql_query)
        )
        rows   = [dict(row._mapping) for row in result.fetchall()]
    
    filtered = filter_columns(rows, user["role"])
    return {
        "role": user["role"],
        "original_columns": list(rows[0].keys()) if rows else [],
        "filtered_columns": list(filtered[0].keys()) if filtered else [],
        "sample_rows": filtered[:5],
    }


# ---------------------------------------------------------------------------
# Audit log viewer — requires admin:audit:read permission
# ---------------------------------------------------------------------------

@app.get("/admin/audit-logs")
def get_audit_logs_endpoint(
    limit: int = 100,
    action_type: str | None = None,
    user: dict = Depends(require_permission("admin:audit:read")),
):
    from security.audit_service import get_audit_logs
    return get_audit_logs(company_id=user["company_id"], limit=limit, action_type=action_type)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(role_router)
app.include_router(user_role_router)
app.include_router(provider_router)
app.include_router(provider_credentials_router)
app.include_router(connection_router)



def get_active_conn_or_raise() -> dict:
    conn = ConnectionService.get_active_connection_global()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active database connection configured."
        )
    return conn

@app.get("/test-column-filter")
def test_column_filter():

    from services.column_display_service import ColumnDisplayService

    rows = [
        {
            "ProductKey": 101,
            "Product": "Shirt",
            "Sales": 25000,
            "EmployeeKey": 10
        }
    ]

    rows = ColumnDisplayService.apply_display_config(
        rows,
        "6692FD9B-A032-43CA-A39E-F13AE1CAA208"   # use one of your real connection IDs
    )

    return rows

@app.get("/test-semantic")
def test_semantic():

    active_connection = get_active_conn_or_raise()

    SemanticDiscoveryService.discover(
        active_connection["connection_id"]
    )

    return {
        "success": True
    }

    


@app.get("/test-resolver/{question}")
def test_resolver(question: str):

    active_connection = get_active_conn_or_raise()

    result = (
        SemanticResolver
        .resolve(
            active_connection["connection_id"],
            question
        )
    )

    return result


@app.get("/test-semantic-context")
def test_semantic_context():

    active_connection = get_active_conn_or_raise()

    semantic_result = SemanticResolver.resolve(
        active_connection["connection_id"],
        "Show Gross Profit by Sales Region"  # or any test query
    )

    return {
        "context": SemanticContextService.build_context(
            semantic_result["metric_objects"],
            semantic_result["dimension_objects"]
        )
    }

@app.get("/semantic/metrics")
def get_semantic_metrics():

    active_connection = get_active_conn_or_raise()

    return SemanticService.get_metrics(
        active_connection["connection_id"]
    )

@app.post("/semantic/metrics")
def create_semantic_metric(
    payload: MetricRequest,
    user: dict = Depends(require_permission("semantic:write"))
):

    active_connection = get_active_conn_or_raise()

    return SemanticService.create_metric(
        connection_id=active_connection["connection_id"],
        data=payload.model_dump(),
        user=user
    )

@app.put("/semantic/metrics/{metric_id}")
def update_semantic_metric(
    metric_id: str,
    payload: MetricRequest,
    user: dict = Depends(require_permission("semantic:write"))
):

    return SemanticService.update_metric(
        metric_id=metric_id,
        data=payload.model_dump(),
        user=user
    )

@app.delete("/semantic/metrics/{metric_id}")
def delete_semantic_metric(
    metric_id: str,
    user: dict = Depends(require_permission("semantic:write"))
):

    return SemanticService.delete_metric(metric_id)

@app.get("/semantic/dimensions")
def get_semantic_dimensions():

    active_connection = get_active_conn_or_raise()

    return SemanticService.get_dimensions(
        active_connection["connection_id"]
    )

@app.post("/semantic/dimensions")
def create_semantic_dimension(
    payload: DimensionRequest,
    user: dict = Depends(require_permission("semantic:write"))
):

    active_connection = get_active_conn_or_raise()

    return SemanticService.create_dimension(
        connection_id=active_connection["connection_id"],
        data=payload.model_dump(),
        user=user
    )

@app.put("/semantic/dimensions/{dimension_id}")
def update_semantic_dimension(
    dimension_id: str,
    payload: DimensionRequest,
    user: dict = Depends(require_permission("semantic:write"))
):

    return SemanticService.update_dimension(
        dimension_id=dimension_id,
        data=payload.model_dump(),
        user=user
    )


@app.delete("/semantic/dimensions/{dimension_id}")
def delete_semantic_dimension(
    dimension_id: str,
    user: dict = Depends(require_permission("semantic:write"))
):

    return SemanticService.delete_dimension(dimension_id)


@app.get("/test-relationships")
def test_relationships():

    active_connection = get_active_conn_or_raise()

    return {
        "relationships":
        [
            list(row)
            for row in
            SemanticRelationshipService
            .get_relationships(
                active_connection["connection_id"]
            )
        ]
    }



@app.get("/test-store-example")
def test_store_example():

    QueryExamplesService.store(
        question="Show sales by region",
        sql_query="""
        SELECT Region,
               SUM(Sales)
        FROM Sales
        """,
        connection_id=
        "6692FD9B-A032-43CA-A39E-F13AE1CAA208"
    )

    return {
        "success": True
    }


@app.get("/test-retrieve-examples")
def test_retrieve_examples():

    rows = (
        QueryExamplesService
        .retrieve(
            connection_id=
            "6692FD9B-A032-43CA-A39E-F13AE1CAA208"
        )
    )

    return rows


@app.get("/debug-relationships")
def debug_relationships():

    query = """
    SELECT
        st_source.table_name,
        sc_source.column_name,
        st_target.table_name,
        sc_target.column_name
    FROM schema_relationships sr

    INNER JOIN schema_tables st_source
        ON sr.source_table_id = st_source.table_id

    INNER JOIN schema_columns sc_source
        ON sr.source_column_id = sc_source.column_id

    INNER JOIN schema_tables st_target
        ON sr.target_table_id = st_target.table_id

    INNER JOIN schema_columns sc_target
        ON sr.target_column_id = sc_target.column_id

    WHERE sr.connection_id =
    '6692FD9B-A032-43CA-A39E-F13AE1CAA208'
    """

    with engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()

    return [list(row) for row in rows]


@app.get("/test-relevant-tables")
def test_relevant_tables():

    active_connection = get_active_conn_or_raise()

    return {
        "tables":
        RelevantTableResolver.resolve(
            active_connection["connection_id"],
            "Show internet sales"
        )
    }

@app.get("/test-relevant-schema")
def test_relevant_schema():

    active_connection = get_active_conn_or_raise()

    tables = [
        "Sales",
        "Region"
    ]

    return {
        "schema":
        RelevantSchemaService.get_schema(
            active_connection["connection_id"],
            tables
        )
    }


@app.get("/test-expanded-tables")
def test_expanded_tables():

    active_connection = get_active_conn_or_raise()

    tables = [
    "SalespersonRegion",
    "Sales"
    ]

    expanded = (
        RelationshipExpander.expand(
            active_connection["connection_id"],
            tables
        )
    )

    return {
        "tables": expanded
    }

@app.get("/test-graph-structure")
def test_graph_structure():

    active_connection = get_active_conn_or_raise()

    graph = RelationshipExpander.build_graph(active_connection["connection_id"])

    bridges = (
        RelationshipExpander.find_bridge_tables(
            graph,
            "SalespersonRegion",
            "Sales"
        )
    )
    return {
        "bridges": bridges
    }


@app.get("/test-qdrant")
def test_qdrant():
    if QdrantService.client is None:
        return {
            "status": "unavailable",
            "message": "Qdrant is not enabled in this environment."
        }

    collections = (
        QdrantService.client
        .get_collections()
    )

    return collections.model_dump()


@app.get("/debug/my-permissions")
def debug_my_permissions(
    user: dict = Depends(get_current_user)
):
    from security.rbac_service import get_role_permissions

    roles = user.get("user_roles", [])

    if not roles and user.get("role"):
        roles = [user["role"]]

    permissions = {}

    for role in roles:
        permissions[role] = sorted(
            list(get_role_permissions(role))
        )

    return {
        "role": user.get("role"),
        "user_roles": roles,
        "permissions": permissions
    }

@app.get("/debug/user")
def debug_user(
    user: dict = Depends(get_current_user)
):
    return { 
        "employee_id": user.get("employee_id"),
        "employee_id_type": str(type(user.get("employee_id"))),
        "official_email": user.get("official_email")
    }

    