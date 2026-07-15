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
        company_id=
            user["company_id"],

        provider_id=
            request.provider_id,

        model_name=
            request.model_name,

        purpose=
            request.purpose,

        is_default=
            request.is_default
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