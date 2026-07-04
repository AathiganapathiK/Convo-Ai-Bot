from pydantic import BaseModel
from typing import Optional
from typing import Literal


class CreateConnectionRequest(BaseModel):

    connection_name: str

    database_type: Literal[
        "sqlserver",
        "postgresql",
        "mysql"
    ]

    host: str

    port: Optional[int] = None

    database_name: str

    username: Optional[str] = None

    password: Optional[str] = None

    connection_string: Optional[str] = None

class TestConnectionRequest(
    BaseModel
):  

    use_windows_auth: bool = True


    database_type: Literal[
        "sqlserver",
        "postgresql",
        "mysql"
    ]

    host: str

    port: int | None = None

    database_name: str

    username: str | None = None

    password: str | None = None