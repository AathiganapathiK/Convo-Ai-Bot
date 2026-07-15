from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectionConfig:

    connection_id: str

    company_id: str

    database_type: str

    authentication_type: str

    host: str

    port: Optional[int]

    database_name: str

    username: Optional[str]

    password: Optional[str]

    driver_name: Optional[str]