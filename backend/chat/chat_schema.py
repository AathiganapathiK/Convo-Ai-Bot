from pydantic import BaseModel


class CreateSessionRequest(
    BaseModel
):
    session_name: str


class UpdateSessionRequest(
    BaseModel
):
    session_name: str