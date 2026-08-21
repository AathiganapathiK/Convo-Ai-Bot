from sqlalchemy import text

from database import engine


class ProviderAdminService:

    @staticmethod
    def get_providers(
        company_id: str
    ):

        query = """
        SELECT
            p.provider_id,
            p.provider_name,
            p.provider_type,
            p.base_url,
            p.is_active,
            p.created_at,
            p.masked_api_key,
            h.status,
            h.last_success_at,
            h.last_failure_at,
            h.failure_count,
            h.consecutive_failures,
            h.last_error,
            h.average_response_ms
        FROM llm_providers p
        LEFT JOIN provider_health h ON p.provider_id = h.provider_id
        WHERE p.company_id = :company_id
        ORDER BY p.provider_name
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
            m.is_active,
            p.provider_name,
            p.provider_type,
            p.is_active AS provider_active,
            h.status AS health_status
        FROM llm_models m
        INNER JOIN llm_providers p ON m.provider_id = p.provider_id
        LEFT JOIN provider_health h ON p.provider_id = h.provider_id
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
        purpose: str | None = None,
        is_default: bool = False,
        purposes: list[str] | None = None
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

        # Normalize purposes
        resolved_purposes = []
        if purposes is not None:
            resolved_purposes = list(purposes)
        elif purpose is not None:
            resolved_purposes = [purpose]
            
        if not resolved_purposes:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="At least one capability/purpose is required")

        # Validate purposes
        VALID_PURPOSES = {"sql_generation", "insight", "intent", "chart"}
        for p in resolved_purposes:
            if p not in VALID_PURPOSES:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail=f"Invalid execution purpose: {p}")

        with engine.begin() as connection:
            for p in resolved_purposes:
                # Check for existing duplicate
                exists = connection.execute(
                    text("""
                        SELECT 1 FROM llm_models 
                        WHERE provider_id = :provider_id AND model_name = :model_name AND purpose = :purpose
                    """),
                    {"provider_id": provider_id, "model_name": model_name, "purpose": p}
                ).fetchone()

                if not exists:
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
                    connection.execute(
                        text(query),
                        {
                            "provider_id": provider_id,
                            "model_name": model_name,
                            "purpose": p,
                            "is_default": is_default
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
        # Validate model belongs to company and both model and provider are active
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT m.is_active AS model_active, p.is_active AS provider_active
                    FROM llm_models m
                    INNER JOIN llm_providers p ON m.provider_id = p.provider_id
                    WHERE m.model_id = :model_id AND p.company_id = :company_id
                """),
                {"model_id": model_id, "company_id": company_id}
            ).fetchone()
            
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Model not found or access denied")
            
        if not row.model_active or not row.provider_active:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Cannot set an inactive model or provider as primary route")

        with engine.begin() as connection:
            # Check if this model is already in an active fallback for this company and purpose
            existing_fb = connection.execute(
                text("""
                    SELECT fallback_id, priority_order
                    FROM llm_fallbacks
                    WHERE company_id = :company_id AND purpose = :purpose AND model_id = :model_id AND is_active = 1
                """),
                {"company_id": company_id, "purpose": purpose, "model_id": model_id}
            ).fetchone()

            if existing_fb:
                if existing_fb.priority_order == 1:
                    # Already priority 1, do nothing
                    pass
                else:
                    # Model exists at priority > 1, swap it with current priority 1
                    p1_fb = connection.execute(
                        text("""
                            SELECT fallback_id, model_id
                            FROM llm_fallbacks
                            WHERE company_id = :company_id AND purpose = :purpose AND priority_order = 1 AND is_active = 1
                        """),
                        {"company_id": company_id, "purpose": purpose}
                    ).fetchone()

                    if p1_fb:
                        connection.execute(
                            text("UPDATE llm_fallbacks SET model_id = :m_id WHERE fallback_id = :fb_id"),
                            {"m_id": model_id, "fb_id": p1_fb.fallback_id}
                        )
                        connection.execute(
                            text("UPDATE llm_fallbacks SET model_id = :m_id WHERE fallback_id = :fb_id"),
                            {"m_id": p1_fb.model_id, "fb_id": existing_fb.fallback_id}
                        )
                    else:
                        connection.execute(
                            text("UPDATE llm_fallbacks SET priority_order = 1 WHERE fallback_id = :fb_id"),
                            {"fb_id": existing_fb.fallback_id}
                        )
            else:
                # Model is not in active fallbacks, insert it at priority 1
                p1_fb = connection.execute(
                    text("""
                        SELECT fallback_id
                        FROM llm_fallbacks
                        WHERE company_id = :company_id AND purpose = :purpose AND priority_order = 1 AND is_active = 1
                    """),
                    {"company_id": company_id, "purpose": purpose}
                ).fetchone()

                if p1_fb:
                    # Shift existing active fallbacks down by 1 priority
                    connection.execute(
                        text("""
                            UPDATE llm_fallbacks
                            SET priority_order = priority_order + 1
                            WHERE company_id = :company_id AND purpose = :purpose AND is_active = 1
                        """),
                        {"company_id": company_id, "purpose": purpose}
                    )
                
                # Insert at priority 1
                connection.execute(
                    text("""
                        INSERT INTO llm_fallbacks (company_id, purpose, priority_order, model_id, is_active)
                        VALUES (:company_id, :purpose, 1, :model_id, 1)
                    """),
                    {"company_id": company_id, "purpose": purpose, "model_id": model_id}
                )

            # DEPRECATED: Keep legacy is_default flag in llm_models in sync for compatibility
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