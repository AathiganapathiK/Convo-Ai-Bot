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
