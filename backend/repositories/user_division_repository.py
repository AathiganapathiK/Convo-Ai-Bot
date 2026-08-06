import logging
from typing import Optional
from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)

class UserDivisionRepository:
    @staticmethod
    def get_division(user_id: int, connection=None) -> Optional[str]:
        """
        Retrieves the division_code for a given user_id.
        Returns the division code string, or None if the user is unrestricted or has no record.
        """
        query = """
        SELECT division_code 
        FROM user_division_access 
        WHERE user_id = :user_id
        """
        try:
            if connection:
                result = connection.execute(text(query), {"user_id": user_id}).fetchone()
            else:
                with engine.connect() as conn:
                    result = conn.execute(text(query), {"user_id": user_id}).fetchone()
            if result:
                return result.division_code
            return None
        except Exception as e:
            logger.error(f"Error getting division for user_id {user_id}: {e}")
            raise e

    @staticmethod
    def save_division(user_id: int, division_code: Optional[str], connection=None) -> None:
        """
        Saves (insert or update) the division_code for a given user_id.
        """
        query = """
        IF EXISTS (SELECT 1 FROM user_division_access WHERE user_id = :user_id)
            UPDATE user_division_access 
            SET division_code = :division_code, updated_at = GETDATE() 
            WHERE user_id = :user_id
        ELSE
            INSERT INTO user_division_access (user_id, division_code, created_at, updated_at) 
            VALUES (:user_id, :division_code, GETDATE(), GETDATE())
        """
        try:
            if connection:
                connection.execute(text(query), {"user_id": user_id, "division_code": division_code})
            else:
                with engine.begin() as conn:
                    conn.execute(text(query), {"user_id": user_id, "division_code": division_code})
        except Exception as e:
            logger.error(f"Error saving division for user_id {user_id}: {e}")
            raise e

    @staticmethod
    def delete_division(user_id: int, connection=None) -> None:
        """
        Deletes the division access record for a given user_id.
        """
        query = """
        DELETE FROM user_division_access 
        WHERE user_id = :user_id
        """
        try:
            if connection:
                connection.execute(text(query), {"user_id": user_id})
            else:
                with engine.begin() as conn:
                    conn.execute(text(query), {"user_id": user_id})
        except Exception as e:
            logger.error(f"Error deleting division for user_id {user_id}: {e}")
            raise e
