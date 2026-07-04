from sqlalchemy import text
from database import engine

def save_usage(
    employee_id,
    session_id,
    request_type,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    estimated_cost,
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
    INSERT INTO user_usage
    (
        employee_id,
        session_id,
        request_type,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        estimated_cost,
        company_id
    )
    VALUES
    (
        :employee_id,
        :session_id,
        :request_type,
        :prompt_tokens,
        :completion_tokens,
        :total_tokens,
        :estimated_cost,
        :company_id
    )
    """

    with engine.begin() as connection:
        connection.execute(
            text(query),
            {
                "employee_id":       employee_id,
                "session_id":        session_id,
                "request_type":      request_type,
                "prompt_tokens":     prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens":      total_tokens,
                "estimated_cost":    estimated_cost,
                "company_id":        company_id
            }
        )