import json
from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from sqlalchemy import text

from database import engine

from auth.dependencies import (
    get_current_user
)

from chat.chat_schema import (
    CreateSessionRequest,
    UpdateSessionRequest
)

router = APIRouter()



@router.post("/chat-sessions")
def create_chat_session(
    request: CreateSessionRequest,
    user=Depends(
        get_current_user
    )
):

    query = """
    INSERT INTO chat_sessions
    (
        employee_id,
        company_id,
        session_name
    )
    OUTPUT INSERTED.id
    VALUES
    (
        :employee_id,
        :company_id,
        :session_name
    )
    """

    with engine.begin() as connection:

        session_id = connection.execute(
            text(query),
            {
                "employee_id":
                    user["employee_id"],

                "company_id":
                    user["company_id"],

                "session_name":
                    request.session_name
            }
        ).scalar()

    return {
        "id": session_id,
        "session_name":
            request.session_name
    }



@router.get("/chat-sessions")
def get_chat_sessions(
    user=Depends(
        get_current_user
    )
):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        query = """
        SELECT
            cs.id,
            cs.session_name,
            cs.created_at,
            cs.updated_at
        FROM chat_sessions cs
        WHERE
            cs.company_id = :company_id
        ORDER BY cs.updated_at DESC
        """
        params = {"company_id": user["company_id"]}
    else:
        query = """
        SELECT
            cs.id,
            cs.session_name,
            cs.created_at,
            cs.updated_at
        FROM chat_sessions cs
        WHERE
            cs.employee_id = :employee_id
            AND 
            cs.company_id = :company_id
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
    user=Depends(
        get_current_user
    )
):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        query = """
        UPDATE chat_sessions
        SET
            session_name = :session_name,
            updated_at = GETDATE()
        WHERE
            id = :session_id
            AND company_id = :company_id
        """
        params = {
            "session_name": request.session_name,
            "session_id": session_id,
            "company_id": user["company_id"]
        }
    else:
        query = """
        UPDATE chat_sessions
        SET
            session_name = :session_name,
            updated_at = GETDATE()
        WHERE
            id = :session_id
            AND employee_id = :employee_id
            AND company_id = :company_id
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
        "message":
        "Session renamed successfully"
    }


@router.delete(
    "/chat-sessions/{session_id}"
)
def delete_chat_session(
    session_id: int,
    user=Depends(
        get_current_user
    )
):
    role = user.get("role", "").upper()
    
    with engine.begin() as connection:
        # First check access to session
        if role == "SUPER_ADMIN":
            check_query = "SELECT id FROM chat_sessions WHERE id = :session_id AND company_id = :company_id"
            check_params = {"session_id": session_id, "company_id": user["company_id"]}
        else:
            check_query = "SELECT id FROM chat_sessions WHERE id = :session_id AND employee_id = :employee_id AND company_id = :company_id"
            check_params = {"session_id": session_id, "employee_id": user["employee_id"], "company_id": user["company_id"]}
            
        session_row = connection.execute(text(check_query), check_params).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        connection.execute(
            text("""
            DELETE
            FROM chat_messages
            WHERE session_id = :session_id
            """),
            {
                "session_id":
                    session_id
            }
        )

        result = connection.execute(
            text("""
            DELETE
            FROM chat_sessions
            WHERE
                id = :session_id
            """),
            {
                "session_id":
                    session_id
            }
        )

    return {
        "message":
        "Session deleted successfully"
    }


@router.get(
    "/chat-sessions/{session_id}/messages"
)
def get_session_messages(
    session_id: int,
    user=Depends(
        get_current_user
    )
):
    role = user.get("role", "").upper()
    if role == "SUPER_ADMIN":
        session_check = """
        SELECT id
        FROM chat_sessions
        WHERE
            id = :session_id
            AND company_id = :company_id
        """
        params = {
            "session_id": session_id,
            "company_id": user["company_id"]
        }
    else:
        session_check = """
        SELECT id
        FROM chat_sessions
        WHERE
            id = :session_id
            AND employee_id = :employee_id
            AND company_id = :company_id
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
