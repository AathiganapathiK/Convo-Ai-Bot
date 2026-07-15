from sqlalchemy import text

from database import engine


class ProviderService:

    @staticmethod
    def get_default_provider():

        query = """
        SELECT TOP 1
            p.provider_type,
            m.model_name
        FROM llm_providers p

        INNER JOIN llm_models m
            ON p.provider_id =
               m.provider_id

        WHERE
            p.is_active = 1
            AND
            m.is_default = 1
            AND
            m.is_active = 1
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query)
            )

            row = result.fetchone()

            if not row:
                return None

            return dict(
                row._mapping
            )