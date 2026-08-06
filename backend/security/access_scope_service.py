import logging
from typing import Optional
from repositories.user_division_repository import UserDivisionRepository
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

class AccessScopeService:
    @classmethod
    def resolve_user_division(cls, user: dict) -> Optional[str]:
        """
        Resolves and returns the allowed division for the current user.
        Returns None if the user has unrestricted/all access.
        """
        user_id = user.get("id")
        
        # Fallback to repository lookup if id is not directly in context
        if not user_id:
            employee_id = user.get("employee_id")
            if employee_id:
                user_id = UserRepository.get_user_id_by_employee_id(employee_id)
                
        if not user_id:
            logger.warning("AccessScopeService: Could not resolve user_id for context.")
            return None

        # Return division or None for unrestricted
        return UserDivisionRepository.get_division(user_id)
