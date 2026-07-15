from sqlalchemy import text
from database import engine
from datetime import datetime, timezone
from fastapi import HTTPException, status
from auth.password_utils import verify_password
from auth.jwt_utils import create_access_token

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

    @staticmethod
    def get_user_by_email(email: str):
        query = """
        SELECT *
        FROM users
        WHERE official_email = :email
        """

        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                {"email": email}
            )

            row = result.fetchone()

            if not row:
                return None

            return dict(row._mapping)


    @staticmethod
    def authenticate_user(email: str, password: str):

        user = AuthService.get_user_by_email(email)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is inactive."
            )

        if not verify_password(password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        access_token = create_access_token(
            {
                "email": user["official_email"]
            }
        )

        with engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE users
                    SET last_login = :last_login
                    WHERE employee_id = :employee_id
                """),
                {
                    "last_login": datetime.now(timezone.utc),
                    "employee_id": user["employee_id"]
                }
            )

        return {
            "access_token": access_token,
            "token_type": "Bearer"
        }