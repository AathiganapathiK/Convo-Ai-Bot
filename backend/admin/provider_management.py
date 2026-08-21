from fastapi import (
    APIRouter,
    Depends
)

from security.rbac_service import (
    require_permission
)

from admin.provider_schema import (
    CreateProviderRequest,
    CreateModelRequest
)

from services.provider_admin_service import (
    ProviderAdminService
)

from admin.model_routing_schema import (
    UpdatePurposeModelRequest
)

router = APIRouter(
    tags=["AI Providers"]
)

@router.get("/providers")
def get_providers(
    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    return (
        ProviderAdminService
        .get_providers(
            user["company_id"]
        )
    )


@router.post("/providers")
def create_provider(
    request:
    CreateProviderRequest,

    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    ProviderAdminService.create_provider(
        company_id=
            user["company_id"],

        provider_name=
            request.provider_name,

        provider_type=
            request.provider_type,

        base_url=
            request.base_url
    )

    return {
        "message":
            "Provider created"
    }

@router.get("/models")
def get_models(
    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    return (
        ProviderAdminService
        .get_models(
            user["company_id"]
        )
    )



@router.post("/models")
def create_model(
    request:
    CreateModelRequest,

    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    ProviderAdminService.create_model(
        company_id=user["company_id"],
        provider_id=request.provider_id,
        model_name=request.model_name,
        purpose=request.purpose,
        is_default=request.is_default,
        purposes=request.purposes
    )

    return {
        "message":
            "Model created"
    }


@router.put(
    "/model-routing"
)
def update_model_routing(
    request:
    UpdatePurposeModelRequest,

    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    ProviderAdminService.set_default_model(
        user["company_id"],
        request.purpose,
        request.model_id
    )

    return {
        "message":
        "Model routing updated"
    }


@router.post("/providers/{provider_id}/test")
def test_provider(
    provider_id: str,
    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    from ai.providers.provider_factory import ProviderFactory
    from services.provider_health_service import ProviderHealthService
    import time
    from datetime import datetime, UTC

    company_id = user["company_id"]

    # 1. Fetch provider and validate company ownership
    with engine.connect() as conn:
        provider_row = conn.execute(
            text("""
                SELECT provider_id, provider_type, provider_name, is_active 
                FROM llm_providers 
                WHERE provider_id = :provider_id AND company_id = :company_id
            """),
            {"provider_id": provider_id, "company_id": company_id}
        ).fetchone()

    if not provider_row:
        raise HTTPException(status_code=403, detail="Provider not found or access denied")

    if not provider_row.is_active:
        raise HTTPException(status_code=400, detail="Cannot test an inactive provider")

    provider_type = provider_row.provider_type
    start_time = time.time()

    try:
        provider = ProviderFactory.get_provider(provider_type, company_id=company_id)

        # 2. Connectivity check based on provider protocol
        if provider_type in ["groq", "openai", "nvidia", "openrouter", "custom_openai"]:
            provider.client.models.list(timeout=5.0)
        elif provider_type == "ollama":
            import requests
            response = requests.get(f"{provider.host}/api/tags", timeout=5.0)
            response.raise_for_status()
        else:
            raise ValueError(f"Connection test not implemented for provider type: {provider_type}")

        latency_ms = (time.time() - start_time) * 1000

        # Update provider_health
        ProviderHealthService.mark_success_by_id(provider_id, latency_ms)

        return {
            "status": "success",
            "provider": provider_row.provider_name,
            "latency_ms": round(latency_ms, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        sanitized_error = str(e)

        # Update provider_health
        ProviderHealthService.mark_failure_by_id(provider_id, sanitized_error)

        return {
            "status": "failure",
            "provider": provider_row.provider_name,
            "latency_ms": round(latency_ms, 2),
            "error": sanitized_error,
            "timestamp": datetime.now(UTC).isoformat()
        }


@router.post("/models/{model_id}/test")
def test_model(
    model_id: str,
    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    from ai.providers.provider_factory import ProviderFactory
    from services.provider_health_service import ProviderHealthService
    import time
    from datetime import datetime, UTC

    company_id = user["company_id"]

    # 1. Fetch model and provider, validate company ownership
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT m.model_id, m.model_name, m.purpose, m.is_active AS model_active,
                       p.provider_id, p.provider_type, p.provider_name, p.is_active AS provider_active
                FROM llm_models m
                INNER JOIN llm_providers p ON m.provider_id = p.provider_id
                WHERE m.model_id = :model_id AND p.company_id = :company_id
            """),
            {"model_id": model_id, "company_id": company_id}
        ).fetchone()

    if not row:
        raise HTTPException(status_code=403, detail="Model not found or access denied")

    if not row.model_active or not row.provider_active:
        raise HTTPException(status_code=400, detail="Cannot test an inactive model or provider")

    start_time = time.time()

    try:
        provider = ProviderFactory.get_provider(row.provider_type, company_id=company_id)

        # 2. Executing a minimal completions check with a strict 5-second timeout
        completion = provider.chat_completion(
            model=row.model_name,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            timeout=5.0
        )

        latency_ms = (time.time() - start_time) * 1000

        # Update provider_health
        ProviderHealthService.mark_success_by_id(row.provider_id, latency_ms)

        # Extract returned content if available (for sanity checking)
        content = ""
        if completion and getattr(completion, "choices", None):
            choice = completion.choices[0]
            if choice and getattr(choice, "message", None):
                content = getattr(choice.message, "content", "")

        return {
            "status": "success",
            "provider": row.provider_name,
            "model": row.model_name,
            "latency_ms": round(latency_ms, 2),
            "response": content[:200],
            "error": None,
            "timestamp": datetime.now(UTC).isoformat()
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        sanitized_error = str(e)

        # Update provider_health
        ProviderHealthService.mark_failure_by_id(row.provider_id, sanitized_error)

        return {
            "status": "failure",
            "provider": row.provider_name,
            "model": row.model_name,
            "latency_ms": round(latency_ms, 2),
            "error": sanitized_error,
            "timestamp": datetime.now(UTC).isoformat()
        }


# Phase 3 Admin UI Endpoints
from pydantic import BaseModel

class UpdateProviderRequest(BaseModel):
    provider_name: str
    provider_type: str
    base_url: str | None
    is_active: bool

class UpdateModelRequest(BaseModel):
    model_name: str
    purpose: str | None = None
    purposes: list[str] | None = None
    is_active: bool = True

class SaveApiKeyRequest(BaseModel):
    api_key: str

class AddFallbackRequest(BaseModel):
    purpose: str
    model_id: str

class ReorderFallbacksRequest(BaseModel):
    purpose: str
    ordered_fallback_ids: list[str]


@router.put("/providers/{provider_id}")
def update_provider(
    provider_id: str,
    request: UpdateProviderRequest,
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    company_id = user["company_id"]
    
    query = """
    UPDATE llm_providers
    SET provider_name = :name, provider_type = :type, base_url = :url, is_active = :active, updated_at = GETDATE()
    WHERE provider_id = :p_id AND company_id = :c_id
    """
    with engine.begin() as conn:
        res = conn.execute(
            text(query),
            {
                "name": request.provider_name,
                "type": request.provider_type,
                "url": request.base_url,
                "active": int(request.is_active),
                "p_id": provider_id,
                "c_id": company_id
            }
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Provider not found or access denied")
    return {"message": "Provider updated"}


@router.put("/models/{model_id}")
def update_model(
    model_id: str,
    request: UpdateModelRequest,
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    company_id = user["company_id"]
    
    # 1. Fetch the target model's provider and current model name & purpose
    with engine.connect() as conn:
        m_row = conn.execute(
            text("""
                SELECT m.provider_id, m.model_name, m.purpose
                FROM llm_models m 
                INNER JOIN llm_providers p ON m.provider_id = p.provider_id 
                WHERE m.model_id = :m_id AND p.company_id = :c_id
            """),
            {"m_id": model_id, "c_id": company_id}
        ).fetchone()
        
    if not m_row:
        raise HTTPException(status_code=404, detail="Model not found or access denied")
        
    provider_id = m_row.provider_id
    original_model_name = m_row.model_name

    # 2. Normalize requested purposes
    resolved_purposes = []
    if request.purposes is not None:
        resolved_purposes = list(request.purposes)
    elif request.purpose is not None:
        resolved_purposes = [request.purpose]
        
    if not resolved_purposes:
        raise HTTPException(status_code=400, detail="At least one capability/purpose is required")

    # Validate purposes
    VALID_PURPOSES = {"sql_generation", "insight", "intent", "chart"}
    for p in resolved_purposes:
        if p not in VALID_PURPOSES:
            raise HTTPException(status_code=400, detail=f"Invalid execution purpose: {p}")

    with engine.begin() as conn:
        # Fetch all existing model-purpose rows for this provider_id and original_model_name
        existing_rows = conn.execute(
            text("""
                SELECT model_id, purpose 
                FROM llm_models 
                WHERE provider_id = :p_id AND model_name = :orig_name
            """),
            {"p_id": provider_id, "orig_name": original_model_name}
        ).fetchall()

        existing_by_purpose = {r.purpose: r.model_id for r in existing_rows}

        edit_purpose = m_row.purpose

        if edit_purpose in resolved_purposes:
            # Edit purpose is kept
            to_add = [p for p in resolved_purposes if p not in existing_by_purpose]
            to_keep = [p for p in resolved_purposes if p in existing_by_purpose]
            to_remove = [p for p in existing_by_purpose if p not in resolved_purposes]

            # Check removal safety
            for p in to_remove:
                rem_model_id = existing_by_purpose[p]
                fallback_exists = conn.execute(
                    text("SELECT 1 FROM llm_fallbacks WHERE model_id = :m_id AND is_active = 1"),
                    {"m_id": rem_model_id}
                ).fetchone()
                if fallback_exists:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot remove capability '{p}' because it is currently active in fallback routing."
                    )

            # Remove Safely
            for p in to_remove:
                rem_model_id = existing_by_purpose[p]
                conn.execute(
                    text("DELETE FROM llm_models WHERE model_id = :m_id"),
                    {"m_id": rem_model_id}
                )

            # Update kept rows
            for p in to_keep:
                keep_model_id = existing_by_purpose[p]
                conn.execute(
                    text("""
                        UPDATE llm_models 
                        SET model_name = :name, is_active = :active 
                        WHERE model_id = :m_id
                    """),
                    {
                        "name": request.model_name,
                        "active": int(request.is_active),
                        "m_id": keep_model_id
                    }
                )

            # Add new purpose rows
            for p in to_add:
                conn.execute(
                    text("""
                        INSERT INTO llm_models (provider_id, model_name, purpose, is_default, is_active)
                        VALUES (:p_id, :name, :purpose, 0, :active)
                    """),
                    {
                        "p_id": provider_id,
                        "name": request.model_name,
                        "purpose": p,
                        "active": int(request.is_active)
                    }
                )
        else:
            # Edit purpose is NOT in resolved_purposes (wants to be removed)
            # Check if edit_purpose itself is active in fallback routing
            fallback_exists = conn.execute(
                text("SELECT 1 FROM llm_fallbacks WHERE model_id = :m_id AND is_active = 1"),
                {"m_id": model_id}
            ).fetchone()
            if fallback_exists:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot remove capability '{edit_purpose}' because it is currently active in fallback routing."
                )

            added_purposes = [p for p in resolved_purposes if p not in existing_by_purpose]

            if added_purposes:
                # Reuse target model_id for the first added purpose in-place!
                reused_purpose = added_purposes[0]
                conn.execute(
                    text("""
                        UPDATE llm_models 
                        SET model_name = :name, purpose = :purp, is_active = :active 
                        WHERE model_id = :m_id
                    """),
                    {
                        "name": request.model_name,
                        "purp": reused_purpose,
                        "active": int(request.is_active),
                        "m_id": model_id
                    }
                )

                # Insert the rest of the added purposes
                for p in added_purposes[1:]:
                    conn.execute(
                        text("""
                            INSERT INTO llm_models (provider_id, model_name, purpose, is_default, is_active)
                            VALUES (:p_id, :name, :purpose, 0, :active)
                        """),
                        {
                            "p_id": provider_id,
                            "name": request.model_name,
                            "purpose": p,
                            "active": int(request.is_active)
                        }
                    )

                # Update other kept purposes
                to_keep = [p for p in resolved_purposes if p in existing_by_purpose]
                for p in to_keep:
                    keep_model_id = existing_by_purpose[p]
                    conn.execute(
                        text("""
                            UPDATE llm_models 
                            SET model_name = :name, is_active = :active 
                            WHERE model_id = :m_id
                        """),
                        {
                            "name": request.model_name,
                            "active": int(request.is_active),
                            "m_id": keep_model_id
                        }
                    )

                # Remove other existing purposes that are not resolved_purposes
                to_remove = [p for p in existing_by_purpose if p not in resolved_purposes and p != edit_purpose]
                for p in to_remove:
                    rem_model_id = existing_by_purpose[p]
                    fallback_exists_p = conn.execute(
                        text("SELECT 1 FROM llm_fallbacks WHERE model_id = :m_id AND is_active = 1"),
                        {"m_id": rem_model_id}
                    ).fetchone()
                    if fallback_exists_p:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot remove capability '{p}' because it is currently active in fallback routing."
                        )
                    conn.execute(
                        text("DELETE FROM llm_models WHERE model_id = :m_id"),
                        {"m_id": rem_model_id}
                    )
            else:
                # No new purposes to add. Delete target model_id
                conn.execute(
                    text("DELETE FROM llm_models WHERE model_id = :m_id"),
                    {"m_id": model_id}
                )

                # Update other kept purposes
                to_keep = [p for p in resolved_purposes if p in existing_by_purpose]
                for p in to_keep:
                    keep_model_id = existing_by_purpose[p]
                    conn.execute(
                        text("""
                            UPDATE llm_models 
                            SET model_name = :name, is_active = :active 
                            WHERE model_id = :m_id
                        """),
                        {
                            "name": request.model_name,
                            "active": int(request.is_active),
                            "m_id": keep_model_id
                        }
                    )

                # Remove other existing purposes
                to_remove = [p for p in existing_by_purpose if p not in resolved_purposes and p != edit_purpose]
                for p in to_remove:
                    rem_model_id = existing_by_purpose[p]
                    fallback_exists_p = conn.execute(
                        text("SELECT 1 FROM llm_fallbacks WHERE model_id = :m_id AND is_active = 1"),
                        {"m_id": rem_model_id}
                    ).fetchone()
                    if fallback_exists_p:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot remove capability '{p}' because it is currently active in fallback routing."
                        )
                    conn.execute(
                        text("DELETE FROM llm_models WHERE model_id = :m_id"),
                        {"m_id": rem_model_id}
                    )

    return {"message": "Model updated"}


@router.post("/providers/{provider_id}/api-key")
def save_provider_api_key(
    provider_id: str,
    request: SaveApiKeyRequest,
    user=Depends(require_permission("admin:providers:manage"))
):
    from services.provider_credential_service import ProviderCredentialService
    ProviderCredentialService.save_api_key(
        provider_id=provider_id,
        api_key=request.api_key,
        company_id=user["company_id"]
    )
    return {"message": "API key updated"}


@router.get("/fallbacks")
def get_fallbacks(
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    query = """
    SELECT f.fallback_id, f.purpose, f.priority_order, f.is_active,
           m.model_id, m.model_name, p.provider_name, p.provider_type
    FROM llm_fallbacks f
    INNER JOIN llm_models m ON f.model_id = m.model_id
    INNER JOIN llm_providers p ON m.provider_id = p.provider_id
    WHERE f.company_id = :company_id AND f.is_active = 1
    ORDER BY f.purpose, f.priority_order
    """
    with engine.connect() as conn:
        res = conn.execute(text(query), {"company_id": user["company_id"]}).fetchall()
    return [dict(r._mapping) for r in res]


@router.post("/fallbacks")
def add_fallback(
    request: AddFallbackRequest,
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    company_id = user["company_id"]
    
    # Validate model belongs to company and is active
    with engine.connect() as conn:
        m_row = conn.execute(
            text("""
                SELECT m.is_active 
                FROM llm_models m
                INNER JOIN llm_providers p ON m.provider_id = p.provider_id
                WHERE m.model_id = :m_id AND p.company_id = :c_id
            """),
            {"m_id": request.model_id, "c_id": company_id}
        ).fetchone()
        
    if not m_row:
        raise HTTPException(status_code=403, detail="Model not found or access denied")
        
    if not m_row.is_active:
        raise HTTPException(status_code=400, detail="Cannot add an inactive model as a fallback route")
        
    # Check if already in fallback list (by comparing model name and provider ID to support multi-capability architecture)
    with engine.connect() as conn:
        exists = conn.execute(
            text("""
                SELECT 1 
                FROM llm_fallbacks f
                INNER JOIN llm_models m ON f.model_id = m.model_id
                WHERE f.company_id = :c_id 
                  AND f.purpose = :p 
                  AND f.is_active = 1
                  AND m.model_name = (SELECT model_name FROM llm_models WHERE model_id = :m_id)
                  AND m.provider_id = (SELECT provider_id FROM llm_models WHERE model_id = :m_id)
            """),
            {"c_id": company_id, "p": request.purpose, "m_id": request.model_id}
        ).fetchone()
        
    if exists:
        raise HTTPException(status_code=400, detail="Model is already in fallback list for this purpose")
        
    with engine.begin() as conn:
        # Get next priority order
        max_order_row = conn.execute(
            text("""
                SELECT COALESCE(MAX(priority_order), 0) as max_order 
                FROM llm_fallbacks 
                WHERE company_id = :c_id AND purpose = :p AND is_active = 1
            """),
            {"c_id": company_id, "p": request.purpose}
        ).fetchone()
        
        next_order = max_order_row.max_order + 1
        
        conn.execute(
            text("""
                INSERT INTO llm_fallbacks (company_id, purpose, priority_order, model_id, is_active) 
                VALUES (:c_id, :p, :order, :m_id, 1)
            """),
            {"c_id": company_id, "p": request.purpose, "order": next_order, "m_id": request.model_id}
        )
    return {"message": "Fallback added"}


@router.delete("/fallbacks/{fallback_id}")
def remove_fallback(
    fallback_id: str,
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    company_id = user["company_id"]
    
    with engine.connect() as conn:
        fb = conn.execute(
            text("""
                SELECT purpose, priority_order 
                FROM llm_fallbacks 
                WHERE fallback_id = :fb_id AND company_id = :c_id AND is_active = 1
            """),
            {"fb_id": fallback_id, "c_id": company_id}
        ).fetchone()
        
    if not fb:
        raise HTTPException(status_code=404, detail="Fallback not found")
        
    with engine.begin() as conn:
        # Delete the fallback record
        conn.execute(
            text("DELETE FROM llm_fallbacks WHERE fallback_id = :fb_id"),
            {"fb_id": fallback_id}
        )
        # Re-shift remaining priorities for this purpose
        conn.execute(
            text("""
                UPDATE llm_fallbacks
                SET priority_order = priority_order - 1
                WHERE company_id = :c_id AND purpose = :p AND priority_order > :order AND is_active = 1
            """),
            {"c_id": company_id, "p": fb.purpose, "order": fb.priority_order}
        )
    return {"message": "Fallback removed"}


@router.put("/fallbacks/reorder")
def reorder_fallbacks(
    request: ReorderFallbacksRequest,
    user=Depends(require_permission("admin:providers:manage"))
):
    from sqlalchemy import text
    from database import engine
    from fastapi import HTTPException
    company_id = user["company_id"]
    
    # Validate and update in one transaction
    with engine.begin() as conn:
        # Temporarily shift active priorities by a huge offset to satisfy unique indexes
        conn.execute(
            text("""
                UPDATE llm_fallbacks
                SET priority_order = priority_order + 1000
                WHERE company_id = :c_id AND purpose = :p AND is_active = 1
            """),
            {"c_id": company_id, "p": request.purpose}
        )
        for idx, fb_id in enumerate(request.ordered_fallback_ids):
            order = idx + 1
            res = conn.execute(
                text("""
                    UPDATE llm_fallbacks 
                    SET priority_order = :order 
                    WHERE fallback_id = :fb_id AND company_id = :c_id AND purpose = :p
                """),
                {"order": order, "fb_id": fb_id, "c_id": company_id, "p": request.purpose}
            )
            if res.rowcount == 0:
                raise HTTPException(status_code=400, detail="Invalid fallback ID for reordering")
    return {"message": "Fallbacks reordered"}