import logging
from typing import Optional
from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)

class UserRepository:
    @staticmethod
    def get_user_id_by_employee_id(employee_id: str, connection=None) -> Optional[int]:
        """
        Retrieves the user ID for a given employee ID.
        """
        query = "SELECT id FROM users WHERE employee_id = :employee_id"
        try:
            if connection:
                result = connection.execute(text(query), {"employee_id": employee_id}).fetchone()
            else:
                with engine.connect() as conn:
                    result = conn.execute(text(query), {"employee_id": employee_id}).fetchone()
            if result:
                return result.id
            return None
        except Exception as e:
            logger.error(f"Error fetching user ID for employee_id {employee_id}: {e}")
            raise e

    @staticmethod
    def create_user(user_data: dict, connection) -> int:
        """
        Creates a new user and returns their generated ID.
        """
        query = """
        INSERT INTO users (
            username, password, employee_id, full_name, official_email,
            department, role, company, is_active, company_id, created_at
        )
        OUTPUT INSERTED.id
        VALUES (
            :username, :password, :employee_id, :full_name, :official_email,
            :department, :role, :company, 1, :company_id, GETDATE()
        )
        """
        try:
            result = connection.execute(text(query), user_data)
            return int(result.scalar())
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise e

    @staticmethod
    def update_user(user_id: int, user_data: dict, connection) -> None:
        """
        Updates an existing user.
        """
        query = """
        UPDATE users
        SET
            full_name = :full_name,
            department = :department,
            role = :role,
            company = :company,
            company_id = :company_id,
            location = :location,
            mobile_number = :mobile_number,
            address = :address,
            updated_at = GETDATE()
        WHERE id = :user_id
        """
        try:
            params = {**user_data, "user_id": user_id}
            connection.execute(text(query), params)
        except Exception as e:
            logger.error(f"Error updating user with id {user_id}: {e}")
            raise e

