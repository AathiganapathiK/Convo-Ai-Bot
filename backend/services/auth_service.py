from sqlalchemy import text
from database import engine


class AuthService:

    @staticmethod
    def get_company_by_email(email: str):

        query = """
        SELECT
            u.employee_id,
            u.full_name,
            u.official_email,
            u.role,
            u.department,

            c.company_id,
            c.company_name,
            c.company_code

        FROM users u
        INNER JOIN companies c
            ON u.company_id = c.company_id

        WHERE u.official_email = :email
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "email": email
                }
            )

            row = result.fetchone()

            if not row:
                return None

            return dict(row._mapping)