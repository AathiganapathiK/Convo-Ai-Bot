from collections import defaultdict

MAX_HISTORY = 5

conversation_store = defaultdict(
    lambda: defaultdict(list)
)


def hydrate_history_from_db(employee_id: str, conversation_id: str, company_id: str | None = None) -> list:
    """
    Hydrate recent conversation history from SQL Server chat_messages table
    when in-memory cache is empty.
    """
    try:
        from database import engine
        from sqlalchemy import text

        conv_id_str = str(conversation_id)
        if not conv_id_str.isdigit():
            return []

        session_int = int(conv_id_str)

        # Validate session ownership for user and company
        with engine.connect() as connection:
            if company_id:
                sess_check = connection.execute(
                    text("""
                        SELECT cs.employee_id, u.company_id 
                        FROM chat_sessions cs
                        INNER JOIN users u ON u.employee_id = cs.employee_id
                        WHERE cs.id = :session_id AND cs.employee_id = :employee_id AND u.company_id = :company_id
                    """),
                    {"session_id": session_int, "employee_id": employee_id, "company_id": company_id}
                ).fetchone()
            else:
                sess_check = connection.execute(
                    text("SELECT employee_id FROM chat_sessions WHERE id = :session_id AND employee_id = :employee_id"),
                    {"session_id": session_int, "employee_id": employee_id}
                ).fetchone()

            if not sess_check:
                return []

            # Query recent messages (up to 10 messages for 5 exchanges)
            msg_rows = connection.execute(
                text("""
                    SELECT TOP 10 id, role, message_text, sql_query, created_at
                    FROM chat_messages
                    WHERE session_id = :session_id
                    ORDER BY id DESC
                """),
                {"session_id": session_int}
            ).fetchall()

        if not msg_rows:
            return []

        # Reverse to get chronological order (id ASC)
        msg_rows = list(reversed(msg_rows))

        exchanges = []
        pending_user_q = None

        for row in msg_rows:
            r_dict = dict(row._mapping)
            role = r_dict.get("role", "").upper()
            msg_text = r_dict.get("message_text", "")
            sql_q = r_dict.get("sql_query")

            if role == "USER":
                pending_user_q = msg_text
            elif role == "ASSISTANT":
                if sql_q:
                    q_text = pending_user_q if pending_user_q else (msg_text or "")
                    exchanges.append({
                        "question": q_text,
                        "sql_query": sql_q
                    })
                    pending_user_q = None

        if len(exchanges) > MAX_HISTORY:
            exchanges = exchanges[-MAX_HISTORY:]

        return exchanges
    except Exception as e:
        print(f"Error hydrating conversation history: {e}")
        return []


def get_history(
    employee_id,
    conversation_id="default",
    company_id=None
):

    employee_id = str(employee_id)
    conversation_id = str(conversation_id)

    # Cache hit check
    if conversation_id in conversation_store[employee_id] and len(conversation_store[employee_id][conversation_id]) > 0:
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_memory(source="CACHE", count=len(conversation_store[employee_id][conversation_id]))
        except Exception:
            pass
        return conversation_store[
            employee_id
        ][
            conversation_id
        ]

    # Cache miss: Attempt DB hydration if conversation_id is numeric session ID
    if conversation_id.isdigit():
        hydrated = hydrate_history_from_db(employee_id, conversation_id, company_id=company_id)
        conversation_store[employee_id][conversation_id] = hydrated
        try:
            from semantic.diagnostic_trace import PipelineDiagnosticTracer
            PipelineDiagnosticTracer.record_memory(source="DATABASE", count=len(hydrated))
        except Exception:
            pass
        return hydrated

    return conversation_store[
        employee_id
    ][
        conversation_id
    ]


def add_exchange(
    employee_id,
    question,
    sql_query,
    conversation_id="default",
    semantic_context=None
):
    employee_id = str(employee_id)
    exchange = {
        "question": question,
        "sql_query": sql_query
    }
    if semantic_context is not None:
        exchange["semantic_context"] = semantic_context

    conversation_store[
                            employee_id
                        ][
                            conversation_id
                        ].append(exchange)

    if (
        len(
            conversation_store[
                employee_id
            ][
                conversation_id
            ]
        )
        > MAX_HISTORY
    ):
        conversation_store[
            employee_id
        ][
            conversation_id
        ].pop(0)


"""
Why Store SQL Instead of Summary?

The SQL contains the exact analytical intent.

The summary is only a narrative.

Therefore SQL is far more useful for follow-up questions.
"""

import time

# Session-level pending clarification storage: (employee_id, session_id) -> dict
pending_clarification_store = {}

def get_pending_clarification(employee_id: str, session_id: str) -> dict | None:
    key = (str(employee_id), str(session_id))
    state = pending_clarification_store.get(key)
    if not state:
        return None
    # 5-minute expiration (300 seconds)
    if time.time() - state.get("timestamp", 0) > 300:
        pending_clarification_store.pop(key, None)
        return None
    return state

def set_pending_clarification(employee_id: str, session_id: str, clarification_state: dict) -> None:
    key = (str(employee_id), str(session_id))
    clarification_state["timestamp"] = time.time()
    pending_clarification_store[key] = clarification_state

def clear_pending_clarification(employee_id: str, session_id: str) -> None:
    key = (str(employee_id), str(session_id))
    pending_clarification_store.pop(key, None)