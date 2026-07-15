from sqlalchemy import text

from database import engine


class ProviderHealthService:

    @staticmethod
    def mark_success(
        provider_type: str,
        response_ms: float
    ):

        query = """
        UPDATE provider_health

        SET
            status = 'HEALTHY',

            last_success_at =
                GETDATE(),

            average_response_ms =
                :response_ms,

            updated_at =
                GETDATE()

        WHERE provider_id =
        (
            SELECT TOP 1
                provider_id
            FROM llm_providers
            WHERE provider_type =
                :provider_type
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "provider_type":
                        provider_type,

                    "response_ms":
                        response_ms
                }
            )

    @staticmethod
    def mark_failure(
        provider_type: str,
        error_message: str
    ):

        query = """
        UPDATE provider_health

        SET
            status = 'FAILED',

            last_failure_at =
                GETDATE(),

            failure_count =
                failure_count + 1,

            last_error =
                :error_message,

            updated_at =
                GETDATE()

        WHERE provider_id =
        (
            SELECT TOP 1
                provider_id
            FROM llm_providers
            WHERE provider_type =
                :provider_type
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "provider_type":
                        provider_type,

                    "error_message":
                        error_message[:4000]
                }
            )