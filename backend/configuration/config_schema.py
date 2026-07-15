from pydantic import BaseModel


class UpdateTenantConfigRequest(BaseModel):

    timezone: str

    currency: str

    date_format: str

    sql_dialect: str