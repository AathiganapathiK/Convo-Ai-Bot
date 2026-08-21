from sqlalchemy import text

from database import engine


# DEPRECATED: ModelRoutingService is deprecated.
# Routing and fallback failovers are now dynamically handled at runtime by FallbackService 
# and LLMExecutionService utilizing the llm_fallbacks list mapping.
class ModelRoutingService:

    @staticmethod
    def get_model_for_purpose(
        purpose: str
    ):

        query = """
        SELECT TOP 1
            p.provider_type,
            m.model_name
        FROM llm_models m

        INNER JOIN llm_providers p
            ON p.provider_id =
               m.provider_id

        WHERE
            m.purpose = :purpose
            AND
            m.is_active = 1
            AND
            p.is_active = 1

        ORDER BY
            m.is_default DESC
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "purpose": purpose
                }
            )
    
            row = result.fetchone()

            if not row:
                raise Exception(
                    f"No model configured "
                    f"for purpose '{purpose}'"
                )

            return dict(
                row._mapping
            )