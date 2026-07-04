from pydantic import BaseModel


class UpdatePurposeModelRequest(
    BaseModel
):

    purpose: str

    model_id: str