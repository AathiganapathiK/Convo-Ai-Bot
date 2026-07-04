from fastapi import APIRouter, Depends

from security.rbac_service import require_permission
from auth.dependencies import get_current_user

from services.config_service import ConfigService

from configuration.config_schema import (
    UpdateTenantConfigRequest
)

router = APIRouter()


@router.get("/company")
def get_company(
    user=Depends(get_current_user)
):

    return {
        "company_id":
            user["company_id"],

        "company_name":
            user["company_name"],

        "company_code":
            user["company_code"]
    }

@router.get("/tenant-config")
def get_tenant_config(
    user=Depends(get_current_user)
):

    config = (
        ConfigService.get_company_config(
            user["company_id"]
        )
    )

    return config

@router.put("/tenant-config")
def update_tenant_config(
    request: UpdateTenantConfigRequest,
    user=Depends(require_permission("admin:config:write"))
):

    ConfigService.update_company_config(
        company_id=user["company_id"],

        timezone=request.timezone,

        currency=request.currency,

        date_format=request.date_format,

        sql_dialect=request.sql_dialect
    )

    return {
        "message":
            "Configuration updated successfully"
    }
