from sqlalchemy import text
from database import engine


class APIKeyService:

    @staticmethod
    def get_company_api_keys(
        company_id: str
    ):

        query = """
        SELECT
            api_key_id,
            key_name,
            is_active,
            expires_at,
            created_at
        FROM api_keys
        WHERE company_id = :company_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "company_id":
                        company_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]