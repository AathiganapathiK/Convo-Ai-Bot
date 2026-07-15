from sqlalchemy import text

from database import engine


class ProviderAdminService:

    @staticmethod
    def get_providers(
        company_id: str
    ):

        query = """
        SELECT
            provider_id,
            provider_name,
            provider_type,
            base_url,
            is_active,
            created_at
        FROM llm_providers
        WHERE company_id = :company_id
        ORDER BY provider_name
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


    @staticmethod
    def create_provider(
        company_id: str,
        provider_name: str,
        provider_type: str,
        base_url: str | None
    ):

        query = """
        INSERT INTO llm_providers
        (
            company_id,
            provider_name,
            provider_type,
            base_url,
            is_active
        )
        VALUES
        (
            :company_id,
            :provider_name,
            :provider_type,
            :base_url,
            1
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "company_id":
                        company_id,

                    "provider_name":
                        provider_name,

                    "provider_type":
                        provider_type,

                    "base_url":
                        base_url
                }
            )

        return True

    @staticmethod
    def get_models(company_id: str):

        query = """
        SELECT
            m.model_id,
            m.provider_id,
            m.model_name,
            m.purpose,
            m.is_default,
            m.is_active
        FROM llm_models m
        INNER JOIN llm_providers p ON m.provider_id = p.provider_id
        WHERE p.company_id = :company_id
        ORDER BY
            m.purpose,
            m.model_name
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {"company_id": company_id}
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def create_model(
        company_id: str,
        provider_id: str,
        model_name: str,
        purpose: str,
        is_default: bool
    ):
        # Validate provider belongs to company
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM llm_providers WHERE provider_id = :provider_id AND company_id = :company_id"),
                {"provider_id": provider_id, "company_id": company_id}
            ).fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Provider not found or access denied")

        query = """
        INSERT INTO llm_models
        (
            provider_id,
            model_name,
            purpose,
            is_default,
            is_active
        )
        VALUES
        (
            :provider_id,
            :model_name,
            :purpose,
            :is_default,
            1
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "provider_id":
                        provider_id,

                    "model_name":
                        model_name,

                    "purpose":
                        purpose,

                    "is_default":
                        is_default
                }
            )

        return True


    @staticmethod
    def get_models_by_purpose(company_id: str):

        query = """
        SELECT
            m.model_id,
            m.provider_id,
            m.model_name,
            m.purpose,
            m.is_default,
            m.is_active
        FROM llm_models m
        INNER JOIN llm_providers p ON m.provider_id = p.provider_id
        WHERE p.company_id = :company_id
        ORDER BY
            m.purpose,
            m.model_name
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {"company_id": company_id}
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def set_default_model(
        company_id: str,
        purpose: str,
        model_id: str
    ):
        # Validate model belongs to company
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT 1 FROM llm_models m
                    INNER JOIN llm_providers p ON m.provider_id = p.provider_id
                    WHERE m.model_id = :model_id AND p.company_id = :company_id
                """),
                {"model_id": model_id, "company_id": company_id}
            ).fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Model not found or access denied")

        with engine.begin() as connection:

            connection.execute(
                text("""
                UPDATE m
                SET m.is_default = 0
                FROM llm_models m
                INNER JOIN llm_providers p ON m.provider_id = p.provider_id
                WHERE m.purpose = :purpose AND p.company_id = :company_id
                """),
                {
                    "purpose": purpose,
                    "company_id": company_id
                }
            )

            connection.execute(
                text("""
                UPDATE llm_models
                SET is_default = 1
                WHERE model_id = :model_id
                """),
                {
                    "model_id": model_id
                }
            )

        return True