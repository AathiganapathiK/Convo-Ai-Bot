from sqlalchemy import text

from database import engine


class ProviderHealthService:

    @staticmethod
    def ensure_columns_exist(connection):
        try:
            connection.execute(text("SELECT consecutive_failures FROM provider_health WHERE 1=0"))
        except Exception:
            try:
                connection.execute(text("ALTER TABLE provider_health ADD consecutive_failures INTEGER DEFAULT 0"))
            except Exception:
                pass

    @staticmethod
    def ensure_health_record_exists(connection, provider_id: str):
        ProviderHealthService.ensure_columns_exist(connection)
        row = connection.execute(
            text("SELECT 1 FROM provider_health WHERE provider_id = :provider_id"),
            {"provider_id": provider_id}
        ).fetchone()
        if not row:
            connection.execute(
                text("""
                    INSERT INTO provider_health 
                    (provider_id, status, failure_count, consecutive_failures, updated_at) 
                    VALUES (:provider_id, 'UNKNOWN', 0, 0, GETDATE())
                """),
                {"provider_id": provider_id}
            )

    @staticmethod
    def mark_success_by_id(
        provider_id: str,
        response_ms: float
    ):
        query = """
        UPDATE provider_health
        SET
            status = 'HEALTHY',
            last_success_at = GETDATE(),
            consecutive_failures = 0,
            average_response_ms = :response_ms,
            updated_at = GETDATE()
        WHERE provider_id = :provider_id
        """
        with engine.begin() as connection:
            ProviderHealthService.ensure_health_record_exists(connection, provider_id)
            connection.execute(
                text(query),
                {
                    "provider_id": provider_id,
                    "response_ms": response_ms
                }
            )

    @staticmethod
    def mark_failure_by_id(
        provider_id: str,
        error_message: str
    ):
        query = """
        UPDATE provider_health
        SET
            status = 'FAILED',
            last_failure_at = GETDATE(),
            failure_count = failure_count + 1,
            consecutive_failures = consecutive_failures + 1,
            last_error = :error_message,
            updated_at = GETDATE()
        WHERE provider_id = :provider_id
        """
        with engine.begin() as connection:
            ProviderHealthService.ensure_health_record_exists(connection, provider_id)
            connection.execute(
                text(query),
                {
                    "provider_id": provider_id,
                    "error_message": error_message[:4000]
                }
            )

    @staticmethod
    def mark_success(
        provider_type: str,
        response_ms: float
    ):
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT TOP 1 provider_id FROM llm_providers WHERE provider_type = :provider_type"),
                {"provider_type": provider_type}
            ).fetchone()
            if row:
                provider_id = row.provider_id
                ProviderHealthService.ensure_health_record_exists(connection, provider_id)
                
                query = """
                UPDATE provider_health
                SET
                    status = 'HEALTHY',
                    last_success_at = GETDATE(),
                    consecutive_failures = 0,
                    average_response_ms = :response_ms,
                    updated_at = GETDATE()
                WHERE provider_id = :provider_id
                """
                connection.execute(
                    text(query),
                    {
                        "provider_id": provider_id,
                        "response_ms": response_ms
                    }
                )

    @staticmethod
    def mark_failure(
        provider_type: str,
        error_message: str
    ):
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT TOP 1 provider_id FROM llm_providers WHERE provider_type = :provider_type"),
                {"provider_type": provider_type}
            ).fetchone()
            if row:
                provider_id = row.provider_id
                ProviderHealthService.ensure_health_record_exists(connection, provider_id)
                
                query = """
                UPDATE provider_health
                SET
                    status = 'FAILED',
                    last_failure_at = GETDATE(),
                    failure_count = failure_count + 1,
                    consecutive_failures = consecutive_failures + 1,
                    last_error = :error_message,
                    updated_at = GETDATE()
                WHERE provider_id = :provider_id
                """
                connection.execute(
                    text(query),
                    {
                        "provider_id": provider_id,
                        "error_message": error_message[:4000]
                    }
                )