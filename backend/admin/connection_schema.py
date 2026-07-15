from pydantic import model_validator
from pydantic import BaseModel
from typing import Optional
from typing import Literal

class BaseConnectionRequest(BaseModel):

    database_type: Literal[
        "sqlserver",
        "postgresql",
        "mysql",
        "sqlite"
    ]

    authentication_type: Literal[
        "SQL",
        "WINDOWS"
    ] = "SQL"

    host: str

    port: Optional[int] = None

    database_name: str

    username: Optional[str] = None

    password: Optional[str] = None

    @model_validator(mode="after")
    def validate_authentication(self):

        if (
            self.authentication_type == "SQL"
            and (
                not self.username
                or not self.password
            )
        ):
            raise ValueError(
                "Username and Password are required for SQL Authentication."
            )

        return self


class CreateConnectionRequest(BaseConnectionRequest):

    connection_name: str
    connection_string: Optional[str] = None


class TestConnectionRequest(BaseConnectionRequest):
    pass
