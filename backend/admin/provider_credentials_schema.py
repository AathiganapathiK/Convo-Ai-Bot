from pydantic import BaseModel


class SaveProviderKeyRequest(
    BaseModel
):

    provider_id: str

    api_key: str