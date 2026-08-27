import json
from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from sqlalchemy import text

from database import engine

from security.rbac_service import require_permission
from security.access_scope_service import AccessScopeService

router = APIRouter()

@router.post("/chat-sessions")
def create_chat_session(
    request: CreateSessionRequest,
    user=Depends(require_permission("chat:ask"))
):
    division_code = AccessScopeService.resolve_user_division(user)

    query = """
    INSERT INTO chat_sessions
    (
        employee_id,
        session_name,
        division_code
    )
    OUTPUT INSERTED.id
    VALUES
    (
        :employee_id,
        :session_name,
        :division_code
    )
    """

    with engine.begin() as connection:
        session_id = connection.execute(
            text(query),
            {
                "employee_id": user["employee_id"],
                "session_name": request.session_name,
                "division_code": division_code
            }
        ).scalar()

    return {
        "id": session_id,
        "session_name": request.session_name,
        "division_code": division_code
    }


@router.get("/chat-sessions")
def get_chat_sessions(
    user=Depends(require_permission("chat:history"))
):
    role = user.get("role", "").upper()
    division_code = AccessScopeService.resolve_user_division(user)

    if role == "SUPER_ADMIN":
        query = """
        SELECT
            cs.id,
            cs.session_name,
            cs.division_code,
            cs.created_at,
            cs.updated_at
        FROM chat_sessions cs
        INNER JOIN users u ON u.employee_id = cs.employee_id
        WHERE
            u.company_id = :company_id
        ORDER BY cs.updated_at DESC
        """
        params = {"company_id": user["company_id"]}
    else:
        # Non-SUPER_ADMIN users can access sessions in their authorized division (Sales -> Sales allowed, Sales -> Manufacturing denied)
        if division_code:
            query = """
            SELECT
                cs.id,
                cs.session_name,
                cs.division_code,
                cs.created_at,
                cs.updated_at
            FROM chat_sessions cs
            INNER JOIN users u ON u.employee_id = cs.employee_id
            WHERE
                u.company_id = :company_id
                AND (cs.employee_id = :employee_id OR cs.division_code = :division_code)
                AND cs.division_code IS NOT NULL
            ORDER BY cs.updated_at DESC
            """
            params = {
                "employee_id": user["employee_id"],
                "company_id": user["company_id"],
                "division_code": division_code
            }
        else:
            query = """
            SELECT
                cs.id,
                cs.session_name,
                cs.division_code,
                cs.created_at,
                cs.updated_at
            FROM chat_sessions cs
            INNER JOIN users u ON u.employee_id = cs.employee_id
            WHERE
                cs.employee_id = :employee_id
                AND u.company_id = :company_id
            ORDER BY cs.updated_at DESC
            """
            params = {"employee_id": user["employee_id"], "company_id": user["company_id"]}

    with engine.connect() as connection:
        result = connection.execute(text(query), params)
        sessions = [
            dict(row._mapping)
            for row in result.fetchall()
        ]

    return sessions


@router.put("/chat-sessions/{session_id}")
def rename_chat_session(
    session_id: int,
    request: UpdateSessionRequest,
    user=Depends(require_permission("chat:history"))
):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        query = """
        UPDATE cs
        SET
            cs.session_name = :session_name,
            cs.updated_at = GETDATE()
        FROM chat_sessions cs
        INNER JOIN users u ON u.employee_id = cs.employee_id
        WHERE
            cs.id = :session_id
            AND u.company_id = :company_id
        """
        params = {
            "session_name": request.session_name,
            "session_id": session_id,
            "company_id": user["company_id"]
        }
    else:
        query = """
        UPDATE cs
        SET
            cs.session_name = :session_name,
            cs.updated_at = GETDATE()
        FROM chat_sessions cs
        INNER JOIN users u ON u.employee_id = cs.employee_id
        WHERE
            cs.id = :session_id
            AND cs.employee_id = :employee_id
            AND u.company_id = :company_id
        """
        params = {
            "session_name": request.session_name,
            "session_id": session_id,
            "employee_id": user["employee_id"],
            "company_id": user["company_id"]
        }

    with engine.begin() as connection:
        result = connection.execute(text(query), params)

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    return {
        "message": "Session renamed successfully"
    }


@router.delete(
    "/chat-sessions/{session_id}"
)
def delete_chat_session(
    session_id: int,
    user=Depends(require_permission("chat:delete"))
):
    role = user.get("role", "").upper()
    
    with engine.begin() as connection:
        # First check access to session
        if role == "SUPER_ADMIN":
            check_query = """
            SELECT cs.id 
            FROM chat_sessions cs 
            INNER JOIN users u ON u.employee_id = cs.employee_id 
            WHERE cs.id = :session_id AND u.company_id = :company_id
            """
            check_params = {"session_id": session_id, "company_id": user["company_id"]}
        else:
            check_query = """
            SELECT cs.id 
            FROM chat_sessions cs 
            INNER JOIN users u ON u.employee_id = cs.employee_id 
            WHERE cs.id = :session_id AND cs.employee_id = :employee_id AND u.company_id = :company_id
            """
            check_params = {"session_id": session_id, "employee_id": user["employee_id"], "company_id": user["company_id"]}
            
        session_row = connection.execute(text(check_query), check_params).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        connection.execute(
            text("DELETE FROM chat_messages WHERE session_id = :session_id"),
            {"session_id": session_id}
        )

        result = connection.execute(
            text("DELETE FROM chat_sessions WHERE id = :session_id"),
            {"session_id": session_id}
        )

    return {
        "message": "Session deleted successfully"
    }



@router.get(
    "/chat-sessions/{session_id}/messages"
)
def get_session_messages(
    session_id: int,
    user=Depends(require_permission("chat:history"))
):
    role = user.get("role", "").upper()
    division_code = AccessScopeService.resolve_user_division(user)

    if role == "SUPER_ADMIN":
        session_check = """
        SELECT cs.id
        FROM chat_sessions cs
        INNER JOIN users u ON u.employee_id = cs.employee_id
        WHERE
            cs.id = :session_id
            AND u.company_id = :company_id
        """
        params = {
            "session_id": session_id,
            "company_id": user["company_id"]
        }
    else:
        if division_code:
            session_check = """
            SELECT cs.id
            FROM chat_sessions cs
            INNER JOIN users u ON u.employee_id = cs.employee_id
            WHERE
                cs.id = :session_id
                AND u.company_id = :company_id
                AND (cs.employee_id = :employee_id OR cs.division_code = :division_code)
            """
            params = {
                "session_id": session_id,
                "employee_id": user["employee_id"],
                "company_id": user["company_id"],
                "division_code": division_code
            }
        else:
            session_check = """
            SELECT cs.id
            FROM chat_sessions cs
            INNER JOIN users u ON u.employee_id = cs.employee_id
            WHERE
                cs.id = :session_id
                AND cs.employee_id = :employee_id
                AND u.company_id = :company_id
            """
            params = {
                "session_id": session_id,
                "employee_id": user["employee_id"],
                "company_id": user["company_id"]
            }


    query = """
    SELECT
        id,
        role,
        message_text,
        sql_query,
        business_summary,
        result_data,
        chart_metadata,
        followup_questions,
        created_at
    FROM chat_messages
    WHERE session_id = :session_id
    ORDER BY created_at
    """

    with engine.connect() as connection:
        session_result = connection.execute(
            text(session_check),
            params
        )

        if not session_result.fetchone():
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        result = connection.execute(
            text(query),
            {
                "session_id":
                    session_id
            }
        )

        messages = []

        for row in result.fetchall():
            msg = dict(row._mapping)
            if msg.get("followup_questions"):

                try:

                    msg["followup_questions"] = (
                        json.loads(
                            msg["followup_questions"]
                        )
                    )

                except Exception:

                    msg["followup_questions"] = []

            else:

                msg["followup_questions"] = []

            
            if msg.get("chart_metadata"):
                try:
                    msg["chart"] = json.loads(
                        msg["chart_metadata"]
                    )
                except Exception:
                    msg["chart"] = None
            else:
                msg["chart"] = None

            messages.append(msg)

    return messages
