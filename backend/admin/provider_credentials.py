from fastapi import (
    APIRouter,
    Depends
)

from security.rbac_service import (
    require_permission
)

from admin.provider_credentials_schema import (
    SaveProviderKeyRequest
)

from services.provider_credential_service import (
    ProviderCredentialService
)

router = APIRouter(
    tags=["Provider Credentials"]
)


@router.post(
    "/providers/api-key"
)
def save_api_key(
    request:
    SaveProviderKeyRequest,

    user=Depends(
        require_permission(
            "admin:providers:manage"
        )
    )
):

    ProviderCredentialService.save_api_key(
        request.provider_id,
        request.api_key,
        user["company_id"]
    )

    return {
        "message":
            "API key saved"
    }