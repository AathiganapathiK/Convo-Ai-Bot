from sqlalchemy import text
from database import engine

def save_query_history(
    employee_id,
    session_id,
    question,
    sql_query,
    execution_status,
    execution_time,
    company_id=None
):
    # Resolve company_id from users if not passed
    if not company_id:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT company_id FROM users WHERE employee_id = :emp_id"),
                    {"emp_id": employee_id}
                ).fetchone()
                if row:
                    company_id = row.company_id
        except Exception:
            pass

    query = """
    INSERT INTO user_queries
    (
        employee_id,
        session_id,
        question,
        sql_query,
        execution_status,
        execution_time,
        company_id
    )
    VALUES
    (
        :employee_id,
        :session_id,
        :question,
        :sql_query,
        :execution_status,
        :execution_time,
        :company_id
    )
    """

    with engine.begin() as connection:
        connection.execute(
            text(query),
            {
                "employee_id":      employee_id,
                "session_id":       session_id,
                "question":         question,
                "sql_query":        sql_query,
                "execution_status": execution_status,
                "execution_time":   execution_time,
                "company_id":       company_id
            }
        )