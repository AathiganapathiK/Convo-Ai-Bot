from sqlalchemy import text

from database import engine


class FallbackService:

    @staticmethod
    def get_models_for_purpose(
        purpose: str,
        company_id: str
    ):

        query = """
        SELECT
            p.provider_type,
            m.model_name,
            f.priority_order
        FROM llm_fallbacks f

        INNER JOIN llm_models m
            ON f.model_id =
               m.model_id

        INNER JOIN llm_providers p
            ON m.provider_id =
               p.provider_id

        WHERE
            f.purpose =
                :purpose

            AND
            f.is_active = 1
            AND
            f.company_id = :company_id

        ORDER BY
            f.priority_order
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "purpose": purpose,
                    "company_id": company_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]