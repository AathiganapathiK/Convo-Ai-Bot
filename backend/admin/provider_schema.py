from pydantic import BaseModel


class CreateProviderRequest(
    BaseModel
):
    provider_name: str

    provider_type: str

    base_url: str | None = None


class CreateModelRequest(
    BaseModel
):
    provider_id: str

    model_name: str

    purpose: str

    is_default: bool = False