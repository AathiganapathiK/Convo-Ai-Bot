from sqlalchemy import text

from database import engine

from services.encryption_service import (
    EncryptionService
)


class ProviderCredentialService:

    @staticmethod
    def mask_key(
        key: str
    ):

        if len(key) < 8:
            return "********"

        return (
            key[:4]
            + "********"
            + key[-4:]
        )

    @staticmethod
    def save_api_key(
        provider_id: str,
        api_key: str,
        company_id: str
    ):

        encrypted = (
            EncryptionService
            .encrypt(api_key)
        )

        masked = (
            ProviderCredentialService
            .mask_key(api_key)
        )

        query = """
        UPDATE llm_providers
        SET
            encrypted_api_key =
                :encrypted,

            masked_api_key =
                :masked
        WHERE
            provider_id =
                :provider_id
            AND company_id = :company_id
        """

        with engine.begin() as connection:

            result = connection.execute(
                text(query),
                {
                    "encrypted":
                        encrypted,

                    "masked":
                        masked,

                    "provider_id":
                        provider_id,

                    "company_id":
                        company_id
                }
            )
            
            if result.rowcount == 0:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Provider not found or access denied")

        return True

    @staticmethod
    def get_api_key(
        provider_id: str
    ):

        query = """
        SELECT
            encrypted_api_key
        FROM llm_providers
        WHERE
            provider_id =
                :provider_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "provider_id":
                        provider_id
                }
            )

            row = result.fetchone()

        if not row:
            return None

        return (
            EncryptionService
            .decrypt(
                row.encrypted_api_key
            )
        )

    @staticmethod
    def get_provider_key_by_type(
        provider_type: str,
        company_id: str = None
    ):

        conditions = ["provider_type = :provider_type", "is_active = 1"]
        params = {"provider_type": provider_type}

        if company_id:
            conditions.append("company_id = :company_id")
            params["company_id"] = company_id

        # A provider row with no stored credential must never win this
        # selection, and the row an administrator most recently saved should.
        #
        # Without these two clauses the query was TOP 1 over several active
        # rows of the same provider_type with no ORDER BY, so SQL Server was
        # free to return any of them. It returned one whose encrypted_api_key
        # was empty, this method returned None, and every provider silently
        # fell back to the .env key - which is what "Using fallback .env Groq
        # key" in the logs was reporting while a valid Admin credential sat
        # unused in another row.
        conditions.append("encrypted_api_key IS NOT NULL")
        conditions.append("encrypted_api_key <> ''")

        query = f"""
        SELECT TOP 1
            encrypted_api_key
        FROM llm_providers
        WHERE
            {" AND ".join(conditions)}
        ORDER BY
            updated_at DESC
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                params
            )

            row = result.fetchone()

        if (
            not row
            or
            not row.encrypted_api_key
        ):
            return None

        return (
            EncryptionService
            .decrypt(
                row.encrypted_api_key
            )
        )