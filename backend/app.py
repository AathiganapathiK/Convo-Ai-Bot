from semantic import runtime_context_builder
import core.config
import sys
import core.config
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
from typing import Optional, cast


from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import StreamingResponse, JSONResponse
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
from semantic.dimension_value_index_builder import DimensionValueIndexBuilder
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.semantic_context_service import SemanticContextService
from semantic.semantic_resolver import SemanticResolver
from semantic.relationship_service import SemanticRelationshipService
from semantic.query_examples_service import QueryExamplesService
from services.connection_service import ConnectionService
from semantic.relevant_table_resolver import RelevantTableResolver
from semantic.relevant_schema_service import RelevantSchemaService
from semantic.relationship_expander import RelationshipExpander
from semantic.semantic_service import SemanticService
from semantic.semantic_schema import MetricRequest, DimensionRequest
from core.logger import debug_print as print

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


from core.exceptions import (
    DatasourceLifecycleException,
    EnterpriseException,
    CLSException,
    SQLValidationException,
    InternalSystemException
)

from core.exception_handlers import (
    datasource_exception_handler
)

from chat.chat_sessions import router as chat_router

from configuration.config_routes import (router as config_router)

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


_frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
print("FRONTEND_ORIGIN =", _frontend_origin)


print("APP_ENV =", os.getenv("APP_ENV"))
print("FRONTEND_ORIGIN =", os.getenv("FRONTEND_ORIGIN"))


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
    user: dict = Depends(require_permission("chat:ask")),
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
    
    import datetime
    request_start_time = time.time()
    active_conn = ConnectionService.get_active_connection(user["company_id"])
    conn_id = active_conn["connection_id"] if active_conn else "None"

    # TEMP_PIPELINE_TRACE_REMOVE_LATER
    try:
        from semantic.diagnostic_trace import PipelineDiagnosticTracer
        PipelineDiagnosticTracer.start_trace(question, session_id=session_id, connection_id=conn_id)
    except Exception:
        pass
    
    print("\n========== REQUEST START ==========")
    print(f"Question: {question}")
    print(f"Session ID: {session_id}")
    print(f"User ID: {user.get('employee_id')}")
    print(f"Company ID: {user.get('company_id')}")
    print(f"Connection ID: {conn_id}")
    print(f"Timestamp: {datetime.datetime.now().isoformat()}")
    print("===================================")
    caller_role = user.get("role", "").upper()

    if str(session_row["company_id"]) != str(user["company_id"]):
        raise HTTPException(status_code=403, detail="Access denied: chat session belongs to another company.")

    if caller_role != "SUPER_ADMIN":
        user_div = AccessScopeService.resolve_user_division(user)
        session_div = dict(session_row).get("division_code")
        
        is_same_owner = session_row["employee_id"] == user["employee_id"]
        is_same_division = bool(user_div and session_div and user_div == session_div)

        if not (is_same_owner or is_same_division):
            raise HTTPException(status_code=403, detail="Access denied: cross-division chat session access denied.")


    # Persist user message
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO chat_messages (session_id, role, message_text)
                VALUES (:session_id, 'USER', :message_text)
            """),
            {"session_id": session_id, "message_text": question},
        )

    # --- Clarification Check ---
    from services.conversation_memory import (
        get_pending_clarification,
        set_pending_clarification,
        clear_pending_clarification
    )
    
    pending_state = get_pending_clarification(user["employee_id"], str(session_id))
    selected_candidate = None
    original_question = None
    is_clarification_resume = False
    accumulated_candidates = []

    if pending_state:
        options_map = pending_state["options"]
        original_question = pending_state["original_question"]
        accumulated_candidates = pending_state.get("accumulated_candidates", [])
        if accumulated_candidates is None:
            accumulated_candidates = []
        elif isinstance(accumulated_candidates, dict):
            accumulated_candidates = [accumulated_candidates]
        
        # Clean text for normalization
        import re
        q_clean = question.strip().lower()
        
        # Replace word numbers with digits
        num_mapping = {
            "one": "1", "first": "1",
            "two": "2", "second": "2",
            "three": "3", "third": "3",
            "four": "4", "fourth": "4",
            "five": "5", "fifth": "5"
        }
        for word_num, digit in num_mapping.items():
            q_clean = re.sub(rf"\b{word_num}\b", digit, q_clean)
            
        matched_options = []
        
        # 1. Exact option number
        digit_matches = re.findall(r'\b(?:option|number|no\.?|choice|select|want)?\s*(\d+)\b', q_clean)
        if not digit_matches:
            digit_matches = re.findall(r'\b(\d+)\b', q_clean)
            
        # Ensure we only matched a single unique option ID
        if len(set(digit_matches)) == 1 and digit_matches[0] in options_map:
            matched_options.append(options_map[digit_matches[0]])
            
        if not matched_options:
            # Check if there is text inside quotes (single or double) in the user question
            quoted_match = re.search(r"['\"](.*?)['\"]", question)
            if quoted_match:
                q_extracted = quoted_match.group(1).strip().lower()
            else:
                # Clean conversational prefixes and dimension labels
                q_extracted = q_clean
                fillers = ["i meant", "choose", "select", "want", "like", "use", "mean", "please", "option"]
                for filler in fillers:
                    q_extracted = re.sub(rf"\b{filler}\b", "", q_extracted)
                
                # Strip dimension names / business names of the options
                dim_names = set()
                for opt in options_map.values():
                    if opt.get("dimension"):
                        dim_names.add(opt["dimension"].lower())
                    if opt.get("business_name"):
                        dim_names.add(opt["business_name"].lower())
                
                for dim in dim_names:
                    escaped_dim = re.escape(dim)
                    q_extracted = re.sub(rf"\b{escaped_dim}\b", "", q_extracted)
                
                # Clean up any residual quotes and multiple spaces
                q_extracted = q_extracted.replace("'", "").replace('"', "")
                q_extracted = re.sub(r"\s+", " ", q_extracted).strip()

            # 2 & 3. Normalized / Case-insensitive exact displayed value
            for opt in options_map.values():
                val_norm = opt["value"].lower().replace("'", "").replace('"', "").strip()
                if q_extracted == val_norm:
                    matched_options.append(opt)
                    
            # 4. Unique normalized prefix
            if not matched_options:
                for opt in options_map.values():
                    val_norm = opt["value"].lower().replace("'", "").replace('"', "").strip()
                    if val_norm.startswith(q_extracted) and len(q_extracted) > 0:
                        matched_options.append(opt)
                    
        # Handle matches
        if len(matched_options) == 1:
            selected_candidate = matched_options[0]
            if selected_candidate not in accumulated_candidates:
                accumulated_candidates.append(selected_candidate)
            # Verify CLS
            from security.cls_engine import get_forbidden_columns
            forbidden_cols = get_forbidden_columns(user.get("role", ""))
            target_col = selected_candidate.get("column_name")
            if target_col and target_col.lower() in [c.lower() for c in forbidden_cols]:
                from core.exceptions import CLSException
                ex = CLSException(f"Access denied: column '{target_col}' is restricted.")
                _save_chat_message(
                    session_id=session_id,
                    role="ASSISTANT",
                    message_text=ex.message,
                    result_data=json.dumps(ex.to_dict())
                )
                return JSONResponse(
                    status_code=403,
                    content=ex.to_dict()
                )
            
            question = original_question
            is_clarification_resume = True
            # TEMP_PIPELINE_TRACE_REMOVE_LATER
            try:
                from semantic.diagnostic_trace import PipelineDiagnosticTracer
                PipelineDiagnosticTracer.record_clarification(required=False, selected_candidate=selected_candidate)
            except Exception:
                pass
            
        elif len(matched_options) > 1:
            # Ambiguous selection: return another clarification
            from core.exceptions import AmbiguityException
            options_list = list(options_map.values())
            clean_options = []
            for opt in options_list:
                display_dim = opt.get("dimension") or opt.get("business_name") or opt.get("display_dimension")
                clean_opt = {
                    "option_id": opt["option_id"],
                    "value": opt["value"]
                }
                if display_dim:
                    clean_opt["display_dimension"] = display_dim
                clean_options.append(clean_opt)
            ex = AmbiguityException(
                message="Your selection matches more than one option. Please choose one.",
                details={
                    "original_question": original_question,
                    "ambiguity_type": pending_state.get("ambiguity_type", "SAME_DIMENSION"),
                    "options": clean_options
                }
            )
            # Re-save to keep timestamp fresh
            set_pending_clarification(user["employee_id"], str(session_id), pending_state)
            _save_chat_message(
                session_id=session_id,
                role="ASSISTANT",
                message_text=ex.message,
                result_data=json.dumps(ex.to_dict())
            )
            return JSONResponse(
                status_code=400,
                content=ex.to_dict()
            )
        else:
            # Check for Intent Shift
            has_semantic_intent = False
            try:
                active_conn = ConnectionService.get_active_connection(user["company_id"])
                intent_res = SemanticResolver.resolve(active_conn["connection_id"], question)
                has_semantic_intent = (
                    len(intent_res.get("metric_objects", [])) > 0 or
                    len(intent_res.get("dimension_objects", [])) > 0 or
                    len(intent_res.get("value_matches", [])) > 0
                )
            except Exception:
                pass
                
            if has_semantic_intent:
                # Intent shift: discard the old pending clarification and process normally
                clear_pending_clarification(user["employee_id"], str(session_id))
            else:
                # Invalid selection
                from core.exceptions import AmbiguityException
                options_list = list(options_map.values())
                clean_options = []
                for opt in options_list:
                    display_dim = opt.get("dimension") or opt.get("business_name") or opt.get("display_dimension")
                    clean_opt = {
                        "option_id": opt["option_id"],
                        "value": opt["value"]
                    }
                    if display_dim:
                        clean_opt["display_dimension"] = display_dim
                        clean_opt["dimension"] = display_dim
                    clean_options.append(clean_opt)
                ex = AmbiguityException(
                    message="That selection isn't one of the available options. Please choose one of the listed options.",
                    details={
                        "original_question": original_question,
                        "ambiguity_type": pending_state.get("ambiguity_type", "SAME_DIMENSION"),
                        "options": clean_options
                    }
                )
                _save_chat_message(
                    session_id=session_id,
                    role="ASSISTANT",
                    message_text=ex.message,
                    result_data=json.dumps(ex.to_dict())
                )
                return JSONResponse(
                    status_code=400,
                    content=ex.to_dict()
                )

    if not is_clarification_resume:
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
    pipeline = SecurityPipeline(user, ip_address=client_ip)

    # Analytics path
    session_owner_emp_id = str(session_row["employee_id"]) if session_row else user["employee_id"]
    history = get_history(session_owner_emp_id, str(session_id), company_id=user["company_id"])

    print("\n========== SESSION ==========")
    print(f"Session Loaded: True")
    print(f"Conversation Turns: {len(history) if history else 0}")
    print(f"Previous Context Size: {sum(len(str(h)) for h in history) if history else 0}")
    print(f"Memory Enabled: True")
    print("=============================")

    try:

        # If this is a clarification resume, pass the full accumulated candidates list
        clarified_val = accumulated_candidates if is_clarification_resume else None

        sql_response = generate_sql_query(
            question, 
            history, 
            company_id=user["company_id"], 
            clarified_candidate=clarified_val
        )

        if not sql_response.get("success", True):
            # Check if this is a clarification required response
            if sql_response.get("action") == "CLARIFICATION_REQUIRED":
                error_details = sql_response.get("error", {}).get("details", {})
                original_q = error_details.get("original_question")
                options = error_details.get("options", [])
                
                # Convert options to dict mapped by option_id string
                options_map = {str(opt["option_id"]): opt for opt in options}
                
                set_pending_clarification(
                    user["employee_id"],
                    str(session_id),
                    {
                        "original_question": original_q,
                        "ambiguity_type": error_details.get("ambiguity_type", "SAME_DIMENSION"),
                        "options": options_map,
                        "accumulated_candidates": accumulated_candidates
                    }
                )
                
                # Clean table_name, column_name and normalized_value from public response before returning!
                clean_options = []
                for opt in options:
                    display_dim = opt.get("dimension") or opt.get("business_name") or opt.get("display_dimension")
                    clean_opt = {
                        "option_id": opt["option_id"],
                        "value": opt["value"]
                    }
                    if display_dim:
                        clean_opt["display_dimension"] = display_dim
                    clean_options.append(clean_opt)
                
                # Update details with clean options
                sql_response["error"]["details"]["options"] = clean_options

                # TEMP_PIPELINE_TRACE_REMOVE_LATER
                try:
                    from semantic.diagnostic_trace import PipelineDiagnosticTracer
                    PipelineDiagnosticTracer.record_clarification(required=True, candidate_count=len(options))
                    PipelineDiagnosticTracer.print_final_trace()
                except Exception:
                    pass

            error_info = sql_response.get("error", {})
            error_message = "Error"
            error_dict = {}
            if isinstance(error_info, dict):
                error_message = str(error_info.get("message", "Error"))
                error_dict = error_info
            elif isinstance(error_info, str):
                error_message = error_info
                error_dict = {"message": error_info}
            else:
                error_dict = {"message": str(error_info)} if error_info is not None else {}

            _save_chat_message(
                session_id=session_id,
                role="ASSISTANT",
                message_text=error_message,
                result_data=json.dumps(error_dict)
            )
            return JSONResponse(
                status_code=400,
                content=sql_response
            )

        # Successful continuation: clear the pending state
        if pending_state and selected_candidate:
            clear_pending_clarification(user["employee_id"], str(session_id))

        sql_query = cast(str,sql_response["sql_query"])
        sql_usage = sql_response["usage"]
        semantic_result = sql_response.get("semantic_result")
        runtime_context = sql_response.get("runtime_context")

        sql_prompt_tokens = 0
        sql_completion_tokens = 0
        sql_total_tokens = 0
        if sql_usage is not None:
            pt = getattr(sql_usage, "prompt_tokens", 0)
            ct = getattr(sql_usage, "completion_tokens", 0)
            tt = getattr(sql_usage, "total_tokens", 0)
            if isinstance(pt, int):
                sql_prompt_tokens = pt
            if isinstance(ct, int):
                sql_completion_tokens = ct
            if isinstance(tt, int):
                sql_total_tokens = tt

        save_usage(
            user["employee_id"], session_id, "SQL_GENERATION",
            sql_prompt_tokens, sql_completion_tokens,
            sql_total_tokens, 0, user["company_id"]
        )

        # CLS validation (pre-execution)
        is_allowed, cls_message = pipeline.validate_cls(sql_query)

        # SQL safety validation
        is_valid, validation_message = validate_sql_query(sql_query)

        print("\n========== SQL VALIDATION ==========")
        print("Validation Started: True")
        
        has_blocked_kw = False
        lower_query = sql_query.lower()
        import re
        from ai.sql_validator import BLOCKED_KEYWORDS
        for keyword in BLOCKED_KEYWORDS:
            if re.search(rf"\b{keyword}\b", lower_query):
                has_blocked_kw = True
                print(f"Blocked Keywords: VIOLATION ({keyword.upper()})")
                break
        if not has_blocked_kw:
            print("Blocked Keywords: Checked (No violations)")
            
        print("Schema Validation: NOT IMPLEMENTED")
        print("AST Validation: NOT IMPLEMENTED")
        print(f"Security Validation: {'Passed' if is_allowed else 'Failed: ' + cls_message}")
        print(f"Validation Result: {'PASS' if (is_allowed and is_valid) else 'FAIL'}")
        print("===================================")

        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_sql("validated", sql_query)
        except Exception:
            pass

        if not is_allowed:
            save_query_history(
                user["employee_id"], session_id, question,
                sql_query, "CLS_BLOCKED", 0, user["company_id"]
            )
            raise CLSException(message=cls_message)

        if not is_valid:
            save_query_history(
                user["employee_id"], session_id, question,
                sql_query, "SQL_VALIDATION_FAILED", 0, user["company_id"]
            )
            raise SQLValidationException(message=validation_message)

    except EnterpriseException as ex:
        import traceback
        print("\n========== ERROR ==========")
        print(f"Stage: Request Execution")
        print(f"Exception: {ex.__class__.__name__}")
        print(f"Reason: {ex.message}")
        print(f"Stack Trace:\n{traceback.format_exc()}")
        print("================================")
        _save_chat_message(
            session_id=session_id,
            role="ASSISTANT",
            message_text=ex.message,
            result_data=json.dumps(ex.to_dict()["error"])
        )
        return JSONResponse(
            status_code=400,
            content=ex.to_dict()
        )

    except Exception as ex:
        import traceback
        print("\n========== ERROR ==========")
        print(f"Stage: Request Execution")
        print(f"Exception: {ex.__class__.__name__}")
        print(f"Reason: {str(ex)}")
        print(f"Stack Trace:\n{traceback.format_exc()}")
        print("================================")
        err_exc = InternalSystemException(str(ex))
        _save_chat_message(
            session_id=session_id,
            role="ASSISTANT",
            message_text=err_exc.message,
            result_data=json.dumps(err_exc.to_dict()["error"])
        )
        return JSONResponse(
            status_code=500,
            content=err_exc.to_dict()
        )

    # Enforce row limit
    sql_query = enforce_row_limit(sql_query)

    # RLS injection (database-driven)
    sql_query, rls_meta = pipeline.apply_rls(sql_query)

    start_time = time.time()
    try:
        active_connection = ConnectionService.get_active_connection(user["company_id"])
        if not active_connection:
            raise Exception("No active database connection configured")

        # Resolve division access scope and apply Division RLS
        from security.access_scope_service import AccessScopeService
        from security.division_rls_engine import DivisionRLSEngine

        division_code = AccessScopeService.resolve_user_division(user)
        if division_code:
            connection_id = active_connection["connection_id"]
            sql_query = DivisionRLSEngine.apply_division_rls(sql_query, division_code, connection_id)

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
        keys_count = len(keys) if 'keys' in locals() else 0

        print("\n========== SQL EXECUTION ==========")
        print("Execution Started: True")
        print(f"Execution Time: {execution_time}s")
        print(f"Rows Returned: {len(rows)}")
        print(f"Columns Returned: {keys_count}")
        print("==================================")

        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_sql("executed", sql_query)
            PipelineDiagnosticTracer.record_timing("sql_execution", execution_time)
            PipelineDiagnosticTracer.record_result(len(rows), col_count=keys_count, status="SUCCESS")
        except Exception:
            pass

        connection_id = active_connection["connection_id"]

        summary_response = generate_business_summary(
            question,
            sql_query,
            rows,
            semantic_result=semantic_result,
            runtime_context=runtime_context,
            history=history,
            company_id=user["company_id"],
            connection_id=connection_id
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

        rec_type = chart_metadata.get('recommended_view', 'table') if chart_metadata else 'table'
        reason = chart_metadata.get('insight', 'No specific reason provided') if chart_metadata else 'No chart metadata returned'
        print("\n========== CHART ==========")
        print(f"Recommended Type: {rec_type}")
        print(f"Reason: {reason}")
        print("================================")

        summary_usage      = summary_response["usage"]

        sum_prompt_tokens = 0
        sum_completion_tokens = 0
        sum_total_tokens = 0
        if summary_usage is not None:
            spt = getattr(summary_usage, "prompt_tokens", 0)
            sct = getattr(summary_usage, "completion_tokens", 0)
            stt = getattr(summary_usage, "total_tokens", 0)
            if isinstance(spt, int):
                sum_prompt_tokens = spt
            if isinstance(sct, int):
                sum_completion_tokens = sct
            if isinstance(stt, int):
                sum_total_tokens = stt
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

        # Build semantic_context to store in conversation history
        semantic_context = None
        if semantic_result and isinstance(semantic_result, dict):
            metric_objects = semantic_result.get("metric_objects", [])
            dimension_objects = semantic_result.get("dimension_objects", [])
            value_matches = semantic_result.get("value_matches", [])

            dimensions = []
            for d in dimension_objects:
                dimensions.append({
                    "dimension_name": d.get("dimension_name"),
                    "business_name": d.get("business_name"),
                    "table_name": d.get("table_name"),
                    "column_name": d.get("column_name")
                })
                
            resolved_values = []
            for v in value_matches:
                resolved_values.append({
                    "dimension_id": v.get("dimension_id"),
                    "business_name": v.get("business_name"),
                    "table_name": v.get("table_name"),
                    "column_name": v.get("column_name"),
                    "value": v.get("value"),
                    "normalized_value": v.get("normalized_value", v.get("value").lower() if v.get("value") else "")
                })
                
            metrics = []
            for m in metric_objects:
                metrics.append({
                    "metric_name": m.get("metric_name"),
                    "business_name": m.get("business_name"),
                    "table_name": m.get("table_name"),
                    "column_name": m.get("column_name")
                })

            if dimensions or resolved_values or metrics:
                semantic_context = {
                    "metrics": metrics,
                    "dimensions": dimensions,
                    "resolved_values": resolved_values
                }

        add_exchange(user["employee_id"], question, sql_query, str(session_id), semantic_context=semantic_context)

        save_query_history(
            user["employee_id"], session_id, question,
            sql_query, "SUCCESS", execution_time, user["company_id"]
        )

        # Audit: successful query
        pipeline.audit_query(question, sql_query, status="SUCCESS",
                             extra_metadata={"execution_time": execution_time, "rows": len(rows)})

        total_req_time = round(time.time() - request_start_time, 2)
        sem_time = 0.0
        if isinstance(semantic_result, dict):
            retrieval_data = semantic_result.get("retrieval")
            if isinstance(retrieval_data, dict):
                r_time = retrieval_data.get("time")
                if isinstance(r_time, (int, float)):
                    sem_time = float(r_time)

        sql_gen_time = 0.0
        if isinstance(sql_response, dict):
            g_time = sql_response.get("gen_time")
            if isinstance(g_time, (int, float)):
                sql_gen_time = float(g_time)

        sum_time_val = 0.0
        if isinstance(summary_response, dict):
            s_time = summary_response.get("sum_time")
            if isinstance(s_time, (int, float)):
                sum_time_val = float(s_time)
        
        print("\n========== REQUEST SUMMARY ==========")
        print(f"Total Request Time: {total_req_time}s")
        print(f"Semantic Time: {sem_time}s")
        print(f"SQL Generation Time: {sql_gen_time}s")
        print(f"SQL Execution Time: {execution_time}s")
        print(f"Summary Time: {sum_time_val}s")
        print(f"Total Tokens (if available): {sql_total_tokens + sum_total_tokens}")
        print("Success: True")
        print("=====================================")
                             
        if rows:
            QueryExamplesService.store(
                question=question,
                sql_query=sql_query,
                connection_id=active_connection["connection_id"]
            )

        # TEMP_PIPELINE_TRACE_REMOVE_LATER
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_timing("summary", sum_time_val)
            PipelineDiagnosticTracer.record_context(history)
            PipelineDiagnosticTracer.print_final_trace()
        except Exception:
            pass

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
    if user.get("role", "").upper() == "SYSTEM_ADMIN":
        with engine.connect() as connection:
            result = connection.execute(text("SELECT company_id, company_name, company_code FROM companies WHERE is_active = 1")).fetchall()
            return [
                {
                    "company_id": str(row.company_id),
                    "company_name": row.company_name,
                    "company_code": row.company_code
                }
                for row in result
            ]
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
    
    with engine.connect() as connection:
        # Total executed queries
        total_res = connection.execute(text(
            "SELECT COUNT(*) AS total FROM user_queries WHERE company_id = :cid"
        ), {"cid": company_id}).fetchone()
        total_queries = total_res._mapping["total"] if total_res else 0

        # Average pipeline latency for successful queries
        avg_res = connection.execute(text(
            "SELECT AVG(CAST(execution_time AS FLOAT)) AS avg_latency FROM user_queries WHERE execution_status = 'SUCCESS' AND company_id = :cid"
        ), {"cid": company_id}).fetchone()
        avg_latency = 0.0
        if avg_res:
            val = avg_res._mapping["avg_latency"]
            if val is not None:
                avg_latency = round(float(val), 2)

        # Success percentage
        success_res = connection.execute(text(
            "SELECT COUNT(*) AS success_count FROM user_queries WHERE execution_status = 'SUCCESS' AND company_id = :cid"
        ), {"cid": company_id}).fetchone()
        success_count = success_res._mapping["success_count"] if success_res else 0
        success_pct = (success_count / total_queries * 100) if total_queries else 0
        success_pct = round(success_pct, 2)

        # Security policy blocks (audit logs with denied actions)
        blocks_res = connection.execute(text(
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


@app.get("/semantic/dimension-value-index/status")
def get_dimension_value_index_status(
    user: dict = Depends(require_permission("semantic:write"))
):
    active_connection = get_active_conn_or_raise()
    connection_id = active_connection["connection_id"]

    with engine.connect() as conn:
        active_dimensions = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM semantic_dimensions
                WHERE connection_id = :connection_id
                  AND is_active = 1
            """),
            {"connection_id": connection_id},
        ).scalar() or 0

        indexed_value_rows = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM dimension_value_index
                WHERE connection_id = :connection_id
            """),
            {"connection_id": connection_id},
        ).scalar() or 0

        dimensions_with_values = conn.execute(
            text("""
                SELECT COUNT(DISTINCT semantic_dimension_id)
                FROM dimension_value_index
                WHERE connection_id = :connection_id
            """),
            {"connection_id": connection_id},
        ).scalar() or 0

    return {
        "connection_id": connection_id,
        "active_dimensions": active_dimensions,
        "indexed_value_rows": indexed_value_rows,
        "dimensions_with_values": dimensions_with_values,
    }


@app.post("/semantic/dimension-value-index/rebuild")
def rebuild_dimension_value_index(
    user: dict = Depends(require_permission("semantic:write"))
):
    active_connection = get_active_conn_or_raise()
    connection_id = active_connection["connection_id"]

    try:
        result = DimensionValueIndexBuilder.build_all(connection_id)
        DimensionValueResolver.clear_cache(connection_id)
        return {
            "success": True,
            "message": "Dimension value index rebuilt.",
            "result": result,
        }
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(ex),
        )


@app.post("/semantic/discover")
def run_semantic_discovery(
    user: dict = Depends(require_permission("semantic:write"))
):
    active_connection = get_active_conn_or_raise()
    connection_id = active_connection["connection_id"]

    try:
        SemanticDiscoveryService.discover(connection_id)
        DimensionValueResolver.clear_cache(connection_id)
        return {
            "success": True,
            "message": (
                "Semantic discovery completed. Metrics and dimensions were "
                "refreshed and the dimension value index was rebuilt."
            ),
        }
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(ex),
        )


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

    